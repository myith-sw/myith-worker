"""시드 적재 (확정 Step 1). Core 기동(ddl-auto: validate)의 전제 데이터를 채운다.

한 진입점:  python -m app.seed.load_all
멱등(upsert)이라 여러 번 돌려도 안전하다 (확정 D-13 실행 순서).

NCS 3종(ncs_unit·ncs_certification·skill_ncs_map)은 app/data/ncs_seed/의 기존
시드와 app/ncs 로더를 재사용한다 — 중복 정의하지 않는다. job·job_profile만 여기서 더한다.
"""

from pathlib import Path

SEED_DATA_DIR = Path(__file__).resolve().parent / "data"
