"""로더가 소스로부터 받는 값 객체. 소스(시드/API)가 달라도 이 형태로 맞춘다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NcsUnitRecord:
    code: str
    name: str
    level: int  # 1~8 (I-2)
    is_verified: bool = False  # 실제 NCS 코드 검증 여부 (확정 D-17). 시드 TBD 코드는 False
    description: str | None = None
    major_name: str | None = None
    middle_name: str | None = None
    minor_name: str | None = None
    detail_name: str | None = None


@dataclass(frozen=True)
class NcsCertRecord:
    ncs_unit_code: str
    cert_code: str
    cert_name: str
    unit_type: str | None = None  # 필수/선택 (I-3 abltUnitTypNm)


@dataclass(frozen=True)
class SkillNcsMapRecord:
    skill_code: str
    ncs_unit_code: str
    is_primary: bool
