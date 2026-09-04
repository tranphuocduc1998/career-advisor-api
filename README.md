## Libary
`pip install fastapi uvicorn asyncpg python-dotenv pydantic scikit-learn numpy`

## Libary
3 — Ghi vào requirements.txt
`pip freeze > requirements.txt`

## Sơ đồ cấu trúc bảng:
riasec_types ──────────────────── academic_major_riasec ── academic_majors
                                                               │
                                                    ┌──────────┼──────────┐
                                                    │          │          │
                                             academic_groups  institution_majors
                                                    │          │
                                             academic_fields  campus ── educational_institution
                                                               │
                                             major_admission_combinations
                                                    │
                                             admission_combinations
                                                    │
                                             combination_subjects ── academic_subjects
                                                    │
                                             admission_cutoffs

                                             