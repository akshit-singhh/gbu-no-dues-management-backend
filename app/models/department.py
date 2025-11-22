# app/models/department.py

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Integer, String


class Department(SQLModel, table=True):
    __tablename__ = "departments"

    id: int = Field(
        sa_column=Column(Integer, primary_key=True, autoincrement=True)
    )

    name: str = Field(
        sa_column=Column(String, unique=True, nullable=False)
    )

    sequence_order: int = Field(
        sa_column=Column(Integer, unique=True, nullable=False)
    )
