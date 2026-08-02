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


class Skill(StrEnum):
    WRITING = "WRITING"
