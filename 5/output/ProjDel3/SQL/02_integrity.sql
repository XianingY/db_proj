-- 第三阶段：在原 13 张表上落实跨表、时间与并发完整性。
-- PostgreSQL 18；所有写事务使用 READ COMMITTED。
-- 延迟检查允许先建实体再建关系，但事务提交前必须全部一致。

CREATE FUNCTION lab_serialize_write() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION '本应用写事务必须使用 READ COMMITTED 隔离级别'
            USING ERRCODE = '23514';
    END IF;
    -- 同一个实验室的小型演示负载，统一事务锁避免写偏斜。
    -- 不同 schema 的同锁只会增加等待，不会改变数据。
    PERFORM pg_advisory_xact_lock(1717, 3);
    -- 标记本事务存在未校验的写入，使延迟约束触发器每批只执行一次全库检查。
    PERFORM set_config('lab.integrity_dirty', '1', true);
    RETURN NULL;
END;
$$;

CREATE FUNCTION lab_usage_before() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE device_state TEXT;
        local_now TIMESTAMP := clock_timestamp() AT TIME ZONE 'Asia/Shanghai';
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM 1 FROM device
        WHERE equipment_id = OLD.equipment_id AND device_number = OLD.device_number
        FOR UPDATE;
        RETURN OLD;
    END IF;
    PERFORM 1 FROM device
    WHERE (equipment_id, device_number) IN
        ((NEW.equipment_id, NEW.device_number)) FOR UPDATE;
    SELECT status INTO device_state FROM device
    WHERE equipment_id = NEW.equipment_id AND device_number = NEW.device_number;
    IF NEW.started_at > local_now OR NEW.ended_at > local_now THEN
        RAISE EXCEPTION '实际使用的开始/结束时刻不能晚于录入时刻（北京时间）'
            USING ERRCODE = '23514';
    END IF;
    IF device_state = 'retired' THEN
        IF TG_OP = 'INSERT' THEN
            RAISE EXCEPTION '退役装置不能新增使用记录' USING ERRCODE = '23514';
        ELSIF (NEW.equipment_id, NEW.device_number, NEW.member_id, NEW.started_at)
              IS DISTINCT FROM
              (OLD.equipment_id, OLD.device_number, OLD.member_id, OLD.started_at)
              OR NEW.ended_at IS NULL THEN
            RAISE EXCEPTION '不能把使用移入退役装置或重新开始退役装置的使用'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION lab_sync_device_status() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- 不覆盖 retired；退役装置仍有 open usage 时由延迟检查拒绝。
    IF TG_OP <> 'INSERT' THEN
        UPDATE device AS d SET status = CASE WHEN EXISTS (
            SELECT 1 FROM equipment_usage u WHERE u.equipment_id = d.equipment_id
            AND u.device_number = d.device_number AND u.ended_at IS NULL
        ) THEN 'in_use' ELSE 'available' END
        WHERE d.equipment_id = OLD.equipment_id AND d.device_number = OLD.device_number
          AND d.status <> 'retired';
    END IF;
    IF TG_OP <> 'DELETE' THEN
        UPDATE device AS d SET status = CASE WHEN EXISTS (
            SELECT 1 FROM equipment_usage u WHERE u.equipment_id = d.equipment_id
            AND u.device_number = d.device_number AND u.ended_at IS NULL
        ) THEN 'in_use' ELSE 'available' END
        WHERE d.equipment_id = NEW.equipment_id AND d.device_number = NEW.device_number
          AND d.status <> 'retired';
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER usage_validate_before
BEFORE INSERT OR UPDATE OR DELETE ON equipment_usage
FOR EACH ROW EXECUTE FUNCTION lab_usage_before();
CREATE TRIGGER usage_sync_after
AFTER INSERT OR UPDATE OR DELETE ON equipment_usage
FOR EACH ROW EXECUTE FUNCTION lab_sync_device_status();

CREATE FUNCTION lab_assert_integrity() RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM lab_member m
        LEFT JOIN faculty f ON f.member_id = m.member_id
        LEFT JOIN student s ON s.member_id = m.member_id
        LEFT JOIN external_collaborator c ON c.member_id = m.member_id
        WHERE (CASE WHEN f.member_id IS NULL THEN 0 ELSE 1 END
             + CASE WHEN s.member_id IS NULL THEN 0 ELSE 1 END
             + CASE WHEN c.member_id IS NULL THEN 0 ELSE 1 END) <> 1
           OR (m.member_type = 'faculty' AND f.member_id IS NULL)
           OR (m.member_type = 'student' AND s.member_id IS NULL)
           OR (m.member_type = 'collaborator' AND c.member_id IS NULL)
    ) THEN
        RAISE EXCEPTION '每名成员必须恰好属于与 member_type 相符的一个子类'
            USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM lab_member m WHERE NOT EXISTS (
            SELECT 1 FROM project_participation p WHERE p.member_id = m.member_id)
    ) THEN
        RAISE EXCEPTION '每名仍存在的成员至少参加一个项目' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM research_project p WHERE NOT EXISTS (
            SELECT 1 FROM project_participation pp
            WHERE pp.project_id = p.project_id AND pp.member_id = p.leader_id)
    ) THEN
        RAISE EXCEPTION '项目负责人必须保留该项目的参与记录' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM equipment e WHERE NOT EXISTS (
            SELECT 1 FROM device d WHERE d.equipment_id = e.equipment_id)
    ) THEN
        RAISE EXCEPTION '每种设备至少有一台装置' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM publication p WHERE NOT EXISTS (
            SELECT 1 FROM authorship a WHERE a.publication_id = p.publication_id)
    ) THEN
        RAISE EXCEPTION '每项成果至少有一位实验室成员作者' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM mentorship m JOIN student s ON s.member_id = m.mentor_id
        JOIN faculty f ON f.member_id = m.mentee_id
    ) THEN
        RAISE EXCEPTION '学生不能指导教师' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM device d WHERE
        (d.status IN ('available', 'retired') AND EXISTS (
            SELECT 1 FROM equipment_usage u WHERE u.equipment_id = d.equipment_id
            AND u.device_number = d.device_number AND u.ended_at IS NULL))
        OR (d.status = 'in_use' AND NOT EXISTS (
            SELECT 1 FROM equipment_usage u WHERE u.equipment_id = d.equipment_id
            AND u.device_number = d.device_number AND u.ended_at IS NULL))
    ) THEN
        RAISE EXCEPTION '装置状态必须与未结束使用一致；退役前必须结束全部使用'
            USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM equipment_usage a JOIN equipment_usage b
        ON a.equipment_id = b.equipment_id AND a.device_number = b.device_number
        AND a.member_id = b.member_id AND a.usage_id < b.usage_id
        WHERE (a.ended_at IS NULL OR a.ended_at > a.started_at)
          AND (b.ended_at IS NULL OR b.ended_at > b.started_at)
          AND a.started_at < COALESCE(b.ended_at, 'infinity'::timestamp)
          AND b.started_at < COALESCE(a.ended_at, 'infinity'::timestamp)
    ) THEN
        RAISE EXCEPTION '同一成员对同一装置的非空使用区间不能重叠'
            USING ERRCODE = '23514';
    END IF;
    -- 使用人数只可能在非空区间开始时增加。按人 DISTINCT，不按记录数。
    IF EXISTS (
        SELECT 1 FROM equipment_usage a
        WHERE (a.ended_at IS NULL OR a.ended_at > a.started_at)
        AND (SELECT COUNT(DISTINCT b.member_id) FROM equipment_usage b
             WHERE b.equipment_id = a.equipment_id
               AND b.device_number = a.device_number
               AND b.started_at <= a.started_at
               AND (b.ended_at IS NULL OR b.ended_at > a.started_at)) > 3
    ) THEN
        RAISE EXCEPTION '同一装置任意时刻最多由三名不同成员同时使用'
            USING ERRCODE = '23514';
    END IF;
END;
$$;

CREATE FUNCTION lab_check_deferred() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('lab.integrity_dirty', true) IS DISTINCT FROM '1' THEN
        RETURN NULL;
    END IF;
    PERFORM lab_assert_integrity();
    PERFORM set_config('lab.integrity_dirty', '0', true);
    RETURN NULL;
END;
$$;

CREATE FUNCTION lab_forbid_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '不允许 TRUNCATE 绕过必需关系检查，请使用事务内的 DELETE'
        USING ERRCODE = '42501';
END;
$$;

DO $$
DECLARE relation_name TEXT;
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'lab_member','faculty','student','external_collaborator',
        'research_project','project_participation','research_grant',
        'equipment','device','equipment_usage','publication','authorship','mentorship'
    ] LOOP
        EXECUTE format('CREATE TRIGGER serialize_write BEFORE INSERT OR UPDATE OR DELETE
            ON %I FOR EACH STATEMENT EXECUTE FUNCTION lab_serialize_write()', relation_name);
        EXECUTE format('CREATE TRIGGER forbid_truncate BEFORE TRUNCATE
            ON %I FOR EACH STATEMENT EXECUTE FUNCTION lab_forbid_truncate()', relation_name);
        EXECUTE format('CREATE CONSTRAINT TRIGGER check_lab_integrity
            AFTER INSERT OR UPDATE OR DELETE ON %I
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION lab_check_deferred()', relation_name);
    END LOOP;
END;
$$;

CREATE INDEX ix_participation_project ON project_participation(project_id);
CREATE INDEX ix_grant_project ON research_grant(project_id);
CREATE INDEX ix_authorship_publication ON authorship(publication_id);
CREATE INDEX ix_mentorship_mentor ON mentorship(mentor_id);
CREATE INDEX ix_usage_device_time ON equipment_usage(equipment_id, device_number, started_at);
CREATE INDEX ix_usage_member ON equipment_usage(member_id);
