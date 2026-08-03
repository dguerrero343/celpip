from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "STUDENT"
    ADMIN = "ADMIN"


class WritingTaskType(StrEnum):
    EMAIL = "EMAIL"
    SURVEY = "SURVEY"


class Difficulty(StrEnum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class WritingTaskStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class WritingTaskSource(StrEnum):
    HUMAN = "HUMAN"
    AI = "AI"


class WritingAttemptType(StrEnum):
    GUIDED_PRACTICE = "GUIDED_PRACTICE"
    TEST_SIMULATION = "TEST_SIMULATION"


class WritingAttemptStatus(StrEnum):
    PREPARING = "PREPARING"
    WRITING = "WRITING"
    SUBMITTED = "SUBMITTED"
    EXPIRED = "EXPIRED"


class WeaknessTrend(StrEnum):
    NEW = "NEW"
    IMPROVED = "IMPROVED"
    STABLE = "STABLE"
    WORSENED = "WORSENED"


class LearningObjectiveStatus(StrEnum):
    PENDING = "PENDING"
    ACHIEVED = "ACHIEVED"
    PARTIALLY_ACHIEVED = "PARTIALLY_ACHIEVED"
    NOT_ACHIEVED = "NOT_ACHIEVED"


class Skill(StrEnum):
    WRITING = "WRITING"
