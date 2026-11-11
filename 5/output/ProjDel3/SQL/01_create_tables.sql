-- 科研实验室管理系统：建表语句
-- PostgreSQL 18

CREATE TABLE lab_member (
    member_id       VARCHAR(40) NOT NULL,
    full_name       TEXT NOT NULL,
    member_type     VARCHAR(12) NOT NULL,
    join_date       DATE NOT NULL,
    CONSTRAINT pk_lab_member PRIMARY KEY (member_id),
    CONSTRAINT ck_member_id CHECK (btrim(member_id) <> ''),
    CONSTRAINT ck_member_name CHECK (btrim(full_name) <> ''),
    CONSTRAINT ck_member_type CHECK
        (member_type IN ('faculty', 'student', 'collaborator')),
    CONSTRAINT ck_member_join_date CHECK (isfinite(join_date))
);

CREATE TABLE faculty (
    member_id       VARCHAR(40) NOT NULL,
    department      TEXT NOT NULL,
    CONSTRAINT pk_faculty PRIMARY KEY (member_id),
    CONSTRAINT fk_faculty_member FOREIGN KEY (member_id)
        REFERENCES lab_member (member_id),
    CONSTRAINT ck_faculty_department CHECK (btrim(department) <> '')
);

CREATE TABLE student (
    member_id       VARCHAR(40) NOT NULL,
    student_number  VARCHAR(40) NOT NULL,
    academic_level  TEXT NOT NULL,
    major           TEXT NOT NULL,
    CONSTRAINT pk_student PRIMARY KEY (member_id),
    CONSTRAINT uq_student_number UNIQUE (student_number),
    CONSTRAINT fk_student_member FOREIGN KEY (member_id)
        REFERENCES lab_member (member_id),
    CONSTRAINT ck_student_number CHECK (btrim(student_number) <> ''),
    CONSTRAINT ck_student_level CHECK (btrim(academic_level) <> ''),
    CONSTRAINT ck_student_major CHECK (btrim(major) <> '')
);

CREATE TABLE external_collaborator (
    member_id       VARCHAR(40) NOT NULL,
    affiliation     TEXT NOT NULL,
    short_cv        TEXT NOT NULL,
    CONSTRAINT pk_external_collaborator PRIMARY KEY (member_id),
    CONSTRAINT fk_collaborator_member FOREIGN KEY (member_id)
        REFERENCES lab_member (member_id),
    CONSTRAINT ck_collaborator_affiliation CHECK (btrim(affiliation) <> ''),
    CONSTRAINT ck_collaborator_cv CHECK (btrim(short_cv) <> '')
);

CREATE TABLE research_project (
    project_id             VARCHAR(40) NOT NULL,
    title                  TEXT NOT NULL,
    start_date             DATE NOT NULL,
    end_date               DATE,
    planned_duration_days  INTEGER NOT NULL,
    status                 VARCHAR(12) NOT NULL,
    leader_id              VARCHAR(40) NOT NULL,
    CONSTRAINT pk_research_project PRIMARY KEY (project_id),
    CONSTRAINT fk_project_leader FOREIGN KEY (leader_id)
        REFERENCES faculty (member_id),
    CONSTRAINT ck_project_id CHECK (btrim(project_id) <> ''),
    CONSTRAINT ck_project_title CHECK (btrim(title) <> ''),
    CONSTRAINT ck_project_duration CHECK (planned_duration_days > 0),
    CONSTRAINT ck_project_status CHECK (status IN ('active', 'completed', 'paused')),
    CONSTRAINT ck_project_dates CHECK
        (isfinite(start_date) AND (end_date IS NULL OR
         (isfinite(end_date) AND end_date >= start_date))),
    CONSTRAINT ck_completed_project CHECK (status <> 'completed' OR end_date IS NOT NULL)
);

CREATE TABLE project_participation (
    member_id       VARCHAR(40) NOT NULL,
    project_id      VARCHAR(40) NOT NULL,
    project_role    TEXT NOT NULL,
    weekly_hours    NUMERIC(8,2) NOT NULL,
    CONSTRAINT pk_project_participation PRIMARY KEY (member_id, project_id),
    CONSTRAINT fk_participation_member FOREIGN KEY (member_id)
        REFERENCES lab_member (member_id),
    CONSTRAINT fk_participation_project FOREIGN KEY (project_id)
        REFERENCES research_project (project_id),
    CONSTRAINT ck_participation_role CHECK (btrim(project_role) <> ''),
    CONSTRAINT ck_participation_hours CHECK
        (weekly_hours BETWEEN 0 AND 168 AND weekly_hours <> 'NaN'::NUMERIC)
);

CREATE TABLE research_grant (
    grant_id                VARCHAR(40) NOT NULL,
    funding_agency          TEXT NOT NULL,
    budget                  NUMERIC(18,2) NOT NULL,
    start_date              DATE NOT NULL,
    expected_duration_days  INTEGER NOT NULL,
    reporting_requirements  TEXT NOT NULL,
    project_id              VARCHAR(40) NOT NULL,
    CONSTRAINT pk_research_grant PRIMARY KEY (grant_id),
    CONSTRAINT fk_grant_project FOREIGN KEY (project_id)
        REFERENCES research_project (project_id),
    CONSTRAINT ck_grant_id CHECK (btrim(grant_id) <> ''),
    CONSTRAINT ck_grant_agency CHECK (btrim(funding_agency) <> ''),
    CONSTRAINT ck_grant_budget CHECK (budget >= 0 AND budget <> 'NaN'::NUMERIC),
    CONSTRAINT ck_grant_start CHECK (isfinite(start_date)),
    CONSTRAINT ck_grant_duration CHECK (expected_duration_days > 0),
    CONSTRAINT ck_grant_reporting CHECK (btrim(reporting_requirements) <> '')
);

CREATE TABLE equipment (
    equipment_id    VARCHAR(40) NOT NULL,
    equipment_name  TEXT NOT NULL,
    equipment_type  TEXT NOT NULL,
    manual_location TEXT NOT NULL,
    CONSTRAINT pk_equipment PRIMARY KEY (equipment_id),
    CONSTRAINT ck_equipment_id CHECK (btrim(equipment_id) <> ''),
    CONSTRAINT ck_equipment_name CHECK (btrim(equipment_name) <> ''),
    CONSTRAINT ck_equipment_type CHECK (btrim(equipment_type) <> ''),
    CONSTRAINT ck_equipment_manual CHECK (btrim(manual_location) <> '')
);

CREATE TABLE device (
    equipment_id    VARCHAR(40) NOT NULL,
    device_number   VARCHAR(40) NOT NULL,
    purchase_date   DATE NOT NULL,
    status          VARCHAR(12) NOT NULL,
    CONSTRAINT pk_device PRIMARY KEY (equipment_id, device_number),
    CONSTRAINT fk_device_equipment FOREIGN KEY (equipment_id)
        REFERENCES equipment (equipment_id),
    CONSTRAINT ck_device_number CHECK (btrim(device_number) <> ''),
    CONSTRAINT ck_device_purchase CHECK (isfinite(purchase_date)),
    CONSTRAINT ck_device_status CHECK (status IN ('available', 'in_use', 'retired'))
);

CREATE TABLE equipment_usage (
    usage_id        VARCHAR(40) NOT NULL,
    member_id       VARCHAR(40) NOT NULL,
    equipment_id    VARCHAR(40) NOT NULL,
    device_number   VARCHAR(40) NOT NULL,
    started_at      TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
    ended_at        TIMESTAMP(0) WITHOUT TIME ZONE,
    purpose         TEXT NOT NULL,
    CONSTRAINT pk_equipment_usage PRIMARY KEY (usage_id),
    CONSTRAINT fk_usage_member FOREIGN KEY (member_id)
        REFERENCES lab_member (member_id),
    CONSTRAINT fk_usage_device FOREIGN KEY (equipment_id, device_number)
        REFERENCES device (equipment_id, device_number),
    CONSTRAINT ck_usage_id CHECK (btrim(usage_id) <> ''),
    CONSTRAINT ck_usage_dates CHECK
        (isfinite(started_at) AND (ended_at IS NULL OR
         (isfinite(ended_at) AND ended_at >= started_at))),
    CONSTRAINT ck_usage_purpose CHECK (btrim(purpose) <> '')
);

CREATE TABLE publication (
    publication_id     VARCHAR(40) NOT NULL,
    title              TEXT NOT NULL,
    publication_year   SMALLINT NOT NULL,
    publication_month  SMALLINT NOT NULL,
    publication_day    SMALLINT,
    venue              TEXT NOT NULL,
    doi                TEXT,
    CONSTRAINT pk_publication PRIMARY KEY (publication_id),
    CONSTRAINT ck_publication_id CHECK (btrim(publication_id) <> ''),
    CONSTRAINT ck_publication_title CHECK (btrim(title) <> ''),
    CONSTRAINT ck_publication_year CHECK (publication_year BETWEEN 1 AND 9999),
    CONSTRAINT ck_publication_month CHECK (publication_month BETWEEN 1 AND 12),
    CONSTRAINT ck_publication_day CHECK (publication_day IS NULL OR
        (publication_day >= 1 AND publication_day <=
            CASE
                WHEN publication_month = 2 THEN
                    CASE WHEN publication_year % 400 = 0 OR
                        (publication_year % 4 = 0 AND publication_year % 100 <> 0)
                        THEN 29 ELSE 28 END
                WHEN publication_month IN (4, 6, 9, 11) THEN 30
                ELSE 31
            END)),
    CONSTRAINT ck_publication_venue CHECK (btrim(venue) <> ''),
    CONSTRAINT ck_publication_doi CHECK (doi IS NULL OR btrim(doi) <> '')
);

CREATE TABLE authorship (
    member_id       VARCHAR(40) NOT NULL,
    publication_id  VARCHAR(40) NOT NULL,
    CONSTRAINT pk_authorship PRIMARY KEY (member_id, publication_id),
    CONSTRAINT fk_authorship_member FOREIGN KEY (member_id)
        REFERENCES lab_member (member_id),
    CONSTRAINT fk_authorship_publication FOREIGN KEY (publication_id)
        REFERENCES publication (publication_id)
);

CREATE TABLE mentorship (
    mentee_id       VARCHAR(40) NOT NULL,
    mentor_id       VARCHAR(40) NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE,
    CONSTRAINT pk_mentorship PRIMARY KEY (mentee_id),
    CONSTRAINT fk_mentorship_mentee FOREIGN KEY (mentee_id)
        REFERENCES lab_member (member_id),
    CONSTRAINT fk_mentorship_mentor FOREIGN KEY (mentor_id)
        REFERENCES lab_member (member_id),
    CONSTRAINT ck_mentorship_self CHECK (mentee_id <> mentor_id),
    CONSTRAINT ck_mentorship_dates CHECK
        (isfinite(start_date) AND (end_date IS NULL OR
         (isfinite(end_date) AND end_date >= start_date)))
);
