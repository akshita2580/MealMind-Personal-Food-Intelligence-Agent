"""
Test how SQLite compares aware vs naive datetime strings.
This is the CRITICAL test — SQLite does TEXT comparison on datetime columns.
"""
import sqlite3

conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, dt TEXT)")

# Store a naive datetime (like SQLModel does)
conn.execute("INSERT INTO test VALUES (1, '2026-08-16 18:30:00.123456')")

# Query with a timezone-aware string (like SQLAlchemy sends for datetime.now(timezone.utc))
# SQLAlchemy converts datetime.now(timezone.utc) to string like '2026-08-16 18:10:00.123456+00:00'
aware_now_before = "2026-08-16 18:10:00.123456+00:00"
aware_now_after = "2026-08-16 18:40:00.123456+00:00"

# Test: Is the stored naive datetime "less than" the aware string?
result1 = conn.execute("SELECT id FROM test WHERE dt < ?", (aware_now_before,)).fetchall()
result2 = conn.execute("SELECT id FROM test WHERE dt < ?", (aware_now_after,)).fetchall()

print(f"Stored: '2026-08-16 18:30:00.123456' (naive, should expire at 18:30)")
print()
print(f"Query: dt < '{aware_now_before}' (18:10, BEFORE expiry)")
print(f"Result: {result1}")
print(f"Expected: [] (NOT expired, row should NOT be returned)")
print(f"CORRECT: {len(result1) == 0}")
print()
print(f"Query: dt < '{aware_now_after}' (18:40, AFTER expiry)")  
print(f"Result: {result2}")
print(f"Expected: [(1,)] (IS expired, row SHOULD be returned)")
print(f"CORRECT: {len(result2) == 1}")
print()

# The CRITICAL question: does the '+00:00' suffix cause wrong comparisons?
# SQLite text comparison: '2026-08-16 18:30:00.123456' vs '2026-08-16 18:10:00.123456+00:00'
# Character by character: identical up to the seconds digit difference
# '3' vs '1' — '3' > '1', so the stored value is "greater", meaning NOT less than.
# This seems correct...

# But what about edge cases? Let's test with a stored time that should NOT be expired:
conn.execute("INSERT INTO test VALUES (2, '2026-08-16 19:00:00.000000')")
aware_check = "2026-08-16 18:50:00.000000+00:00"

result3 = conn.execute("SELECT id FROM test WHERE dt < ?", (aware_check,)).fetchall()
print(f"Stored: '2026-08-16 19:00:00.000000' (naive, valid until 19:00)")
print(f"Query: dt < '{aware_check}' (18:50+00:00)")
print(f"Result: {result3}")
print(f"Expected: [] (row 2 should NOT be returned)")
print(f"CORRECT: {len(result3) == 0}")
print()

# Now test the ACTUAL edge case — what happens with trailing +00:00 in string comparison?
# '2026-08-16 19:00:00.000000' < '2026-08-16 18:50:00.000000+00:00'
# Position-by-position:
# Index 17: '9' vs '8' — '9' > '8', so stored is NOT less than. Correct!

# But what about THIS scenario:
# Stored: '2026-08-16 17:48:59.014835' (created 15 min ago with 15 min expiry)
# This means it was CREATED at 17:33:59 and expires at 17:48:59
# Now check at 18:08:35.961417+00:00 — should be expired
aware_now = "2026-08-16 18:08:35.961417+00:00"
conn.execute("INSERT INTO test VALUES (3, '2026-08-16 17:48:59.014835')")
result4 = conn.execute("SELECT id FROM test WHERE dt < ?", (aware_now,)).fetchall()
print(f"Stored: '2026-08-16 17:48:59.014835' (should be expired)")
print(f"Query: dt < '{aware_now}'")
print(f"Result: {result4} (should include id=3)")
print(f"CORRECT: {3 in [r[0] for r in result4]}")
print()

# THE BIG TEST: Can the +00:00 suffix EVER cause a valid state to appear expired?
# Store a state that should be valid for 15 more minutes:
conn.execute("INSERT INTO test VALUES (4, '2026-08-16 18:30:00.000000')")
aware_current = "2026-08-16 18:15:00.000000+00:00"
result5 = conn.execute("SELECT id FROM test WHERE dt < ?", (aware_current,)).fetchall()
print(f"Stored: '2026-08-16 18:30:00.000000' (should be valid)")
print(f"Query: dt < '{aware_current}'")
print(f"Result: {result5} (should NOT include id=4)")
valid_ids = [r[0] for r in result5]
print(f"CORRECT: {4 not in valid_ids}")

conn.close()
