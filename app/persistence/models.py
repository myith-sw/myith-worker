"""SQLAlchemy 선언적 Base + 모델.

Worker/오프라인 배치 소유 테이블만 여기 정의한다 (C-1, PART E). Core 소유
테이블의 DDL은 여기 넣지 않는다.

지금까지 정의된 것: 오프라인 배치 소유 3종 (ncs_unit, ncs_certification,
skill_ncs_map). 런타임엔 읽기 전용, 적재는 app/ncs 배치가 한다 (PART K).
"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class NcsUnit(Base):
    """NCS 능력단위. level(1~8)이 난이도 공식의 N값 근거 (F-5, I-2)."""

    __tablename__ = "ncs_unit"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1~8
    major_name: Mapped[str | None] = mapped_column(String, nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String, nullable=True)
    minor_name: Mapped[str | None] = mapped_column(String, nullable=True)
    detail_name: Mapped[str | None] = mapped_column(String, nullable=True)


class NcsCertification(Base):
    """능력단위–자격 종목 연계 (I-3). 한 능력단위에 연계된 자격은 전부 저장."""

    __tablename__ = "ncs_certification"

    ncs_unit_code: Mapped[str] = mapped_column(
        String, ForeignKey("ncs_unit.code"), primary_key=True
    )
    cert_code: Mapped[str] = mapped_column(String, primary_key=True)
    cert_name: Mapped[str] = mapped_column(String, nullable=False)
    unit_type: Mapped[str | None] = mapped_column(String, nullable=True)  # 필수/선택


class SkillNcsMap(Base):
    """스킬 → NCS 능력단위 매핑. is_primary는 스킬당 정확히 하나 (F-4).

    (스킬당 하나만 true) 규칙은 DB 제약으로 강제하기 애매해 적재 단계에서
    검증한다 (app/ncs/skill_map_loader.validate_primary_uniqueness).
    """

    __tablename__ = "skill_ncs_map"

    skill_code: Mapped[str] = mapped_column(String, primary_key=True)
    ncs_unit_code: Mapped[str] = mapped_column(
        String, ForeignKey("ncs_unit.code"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
