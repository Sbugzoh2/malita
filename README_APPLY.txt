Overwrite backend/tiers.py with the one in this folder (Learner price_zar
changed 49.99 -> 99.99, Premium 99.99 -> 129.99 - nothing else changed),
then:

  git add backend/tiers.py
  git commit -m "Raise subscription prices: Learner to R99.99, Premium to R129.99"
  git push origin main

Since the ID number / email uniqueness enforcement you asked about is
already fully implemented (both fields are checked for duplicates and
required at registration, on web and mobile alike), there's no other
file to apply for that part - no code change was needed.
