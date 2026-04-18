# app/models/enums.py

from enum import Enum

class OverallApplicationStatus(str, Enum):
    Pending = "Pending"
    InProgress = "InProgress"
    Completed = "Completed"
    Rejected = "Rejected"

class StageStatus(str, Enum):
    Pending = "Pending"
    Approved = "Approved"
    Rejected = "Rejected"

class PriorityLevel(str, Enum):
    Low = "Low"
    High = "High"