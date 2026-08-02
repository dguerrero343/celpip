from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index

from app.database.base import Base


def test_requested_tables_are_registered() -> None:
    expected = {
        "users",
        "writing_tasks",
        "writing_submissions",
        "writing_evaluations",
        "ai_student_context",
        "user_score_history",
        "ai_usage",
        "writing_task_assignments",
    }
    assert expected == set(Base.metadata.tables)


def test_constraint_names_follow_the_metadata_convention() -> None:
    expected = {
        "users": {
            "ck_users_current_score_range",
            "ck_users_target_score_range",
        },
        "writing_submissions": {"ck_writing_submissions_nonnegative_word_count"},
        "writing_evaluations": {
            "ck_writing_evaluations_estimated_score_range",
            "ck_writing_evaluations_task_score_range",
            "ck_writing_evaluations_organization_score_range",
            "ck_writing_evaluations_vocabulary_score_range",
            "ck_writing_evaluations_grammar_score_range",
        },
        "ai_student_context": {
            "ck_ai_student_context_current_score_range",
            "ck_ai_student_context_target_score_range",
        },
        "user_score_history": {"ck_user_score_history_score_range"},
        "ai_usage": {
            "ck_ai_usage_nonnegative_input_tokens",
            "ck_ai_usage_nonnegative_output_tokens",
            "ck_ai_usage_nonnegative_estimated_cost",
        },
        "writing_tasks": {"ck_writing_tasks_target_score_range"},
    }

    for table_name, names in expected.items():
        table = Base.metadata.tables[table_name]
        actual = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert actual == names


def test_foreign_key_delete_policies_protect_and_remove_owned_data() -> None:
    expected = {
        ("writing_submissions", "user_id"): "CASCADE",
        ("writing_submissions", "task_id"): "RESTRICT",
        ("writing_evaluations", "submission_id"): "CASCADE",
        ("ai_student_context", "user_id"): "CASCADE",
        ("user_score_history", "user_id"): "CASCADE",
        ("ai_usage", "user_id"): "CASCADE",
        ("writing_task_assignments", "user_id"): "CASCADE",
        ("writing_task_assignments", "task_id"): "RESTRICT",
        ("writing_tasks", "reviewed_by"): "SET NULL",
    }

    actual: dict[tuple[str, str], str | None] = {}
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                column_name = next(iter(constraint.columns)).name
                actual[(table.name, column_name)] = constraint.ondelete

    assert actual == expected


def test_query_oriented_composite_indexes_are_registered() -> None:
    expected = {
        "ix_writing_submissions_user_submitted": ("user_id", "submitted_at"),
        "ix_user_score_history_user_date": ("user_id", "date"),
        "ix_ai_usage_user_created": ("user_id", "created_at"),
        "ix_writing_task_assignments_user_assigned": ("user_id", "assigned_at"),
    }
    actual: dict[str, tuple[str, ...]] = {}

    for table in Base.metadata.tables.values():
        for index in table.indexes:
            if isinstance(index, Index) and index.name in expected:
                actual[index.name] = tuple(column.name for column in index.columns)

    assert actual == expected


def test_database_defaults_exist_for_account_state() -> None:
    users = Base.metadata.tables["users"]

    assert users.c.role.server_default is not None
    assert users.c.role.server_default.arg == "STUDENT"
    assert users.c.is_active.server_default is not None
    assert str(users.c.is_active.server_default.arg) == "true"
