"""
Malita (Pty) Ltd — one-off CLI to add the higher-ed segment to an
EXISTING tutor account that only ever applied for (and was approved
for) high school.

There's no self-service "add a segment later" flow in v1 (see
TutorAccount's own docstring in backend/db.py) - a tutor's higher-ed
institution/qualification/year/modules are normally only ever set once,
at apply_as_tutor() time. This script does the same thing an admin
approving a fresh higher-ed application would, but for a tutor who never
submitted one: sets wants_higher_ed=True, the institution/qualification/
year/modules, and higher_ed_status directly to "approved" (skipping
pending_review, since an admin running this from the shell already
trusts the applicant - same high-trust spirit as backend/set_admin.py).

Look up the institution_id/qualification_id/module_id values first via
the Tutoring Admin screen's Higher-Ed Catalog tab (or list_institutions/
list_qualifications/list_modules in a Python shell).

Usage:
    python -m backend.grant_tutor_higher_ed tutor@example.com \\
        --institution-id 1 --qualification-id 3 --year 4 \\
        --modules 10,11,12 [--average 75] [--qualification-complete]

    --year is the tutor's OWN year of study (1-5, see YEAR_LEVEL_LABELS) -
    only modules at least one year behind it are accepted, unless
    --qualification-complete is also passed.
"""

import argparse
import sys

from .db import get_session, TutorAccount, TutorHigherEdModule, Qualification, Module, YEAR_LEVEL_LABELS


def grant_tutor_higher_ed(
    email: str, *, institution_id: int, qualification_id: int, year_of_study: int,
    module_ids: list[int], qualification_complete: bool = False, average: float = 100.0,
) -> None:
    email = email.strip().lower()
    with get_session() as db:
        tutor = db.query(TutorAccount).filter(TutorAccount.email == email).first()
        if not tutor:
            print(f"No tutor account found for {email}.")
            return
        qual = db.query(Qualification).get(qualification_id)
        if not qual or qual.institution_id != institution_id:
            print("That qualification doesn't belong to the given institution.")
            return
        if year_of_study not in YEAR_LEVEL_LABELS:
            print(f"--year must be one of {sorted(YEAR_LEVEL_LABELS)}.")
            return

        tutor.wants_higher_ed = True
        tutor.higher_ed_status = "approved"
        tutor.higher_ed_institution_id = institution_id
        tutor.higher_ed_qualification_id = qualification_id
        tutor.higher_ed_year_of_study = year_of_study
        tutor.higher_ed_qualification_complete = qualification_complete
        tutor.higher_ed_average = average

        added, skipped_ineligible, skipped_existing = 0, [], 0
        for module_id in module_ids:
            mod = db.query(Module).get(module_id)
            if not mod:
                print(f"  module #{module_id} doesn't exist - skipped.")
                continue
            if not qualification_complete and mod.year_level >= year_of_study:
                skipped_ineligible.append(mod.name)
                continue
            existing = db.query(TutorHigherEdModule).filter(
                TutorHigherEdModule.tutor_id == tutor.id, TutorHigherEdModule.module_id == module_id,
            ).first()
            if existing:
                skipped_existing += 1
                continue
            db.add(TutorHigherEdModule(tutor_id=tutor.id, module_id=module_id))
            added += 1

        print(f"Granted higher-ed access for {email} (tutor id {tutor.id}): {added} module(s) added.")
        if skipped_existing:
            print(f"  {skipped_existing} module(s) were already assigned - skipped.")
        if skipped_ineligible:
            print(
                f"  {len(skipped_ineligible)} module(s) skipped (not at least one year behind "
                f"{YEAR_LEVEL_LABELS[year_of_study]}): {', '.join(skipped_ineligible)}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email")
    parser.add_argument("--institution-id", type=int, required=True)
    parser.add_argument("--qualification-id", type=int, required=True)
    parser.add_argument("--year", type=int, required=True, dest="year_of_study")
    parser.add_argument("--modules", required=True, help="Comma-separated module ids, e.g. 10,11,12")
    parser.add_argument("--average", type=float, default=100.0)
    parser.add_argument("--qualification-complete", action="store_true")
    args = parser.parse_args()

    try:
        module_ids = [int(m.strip()) for m in args.modules.split(",") if m.strip()]
    except ValueError:
        print("--modules must be a comma-separated list of integers.")
        sys.exit(1)

    grant_tutor_higher_ed(
        args.email,
        institution_id=args.institution_id,
        qualification_id=args.qualification_id,
        year_of_study=args.year_of_study,
        module_ids=module_ids,
        qualification_complete=args.qualification_complete,
        average=args.average,
    )
