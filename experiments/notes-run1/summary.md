# Notes run 1

## Setup

- Model: Kimi K2.7 Code
- People: 7
- Questions: 40
- Memory limit: 150 words per person
- Arms: facts and implications
- Lookup run: one fresh agent per question and arm, 80 agents total
- Allowed lookup tool: keyword search on that person's `phone.txt`
- Rule violations found in logs: 0

## No lookup

| Person | Facts | Implications |
|---|---:|---:|
| Wei | 2/6 | 4/6 |
| Tomás | 1/6 | 2/6 |
| Priya | 0/6 | 0/6 |
| Devon | 0/5 | 2/5 |
| Alice | 1/6 | 0/6 |
| Hannah | 2/5 | 2/5 |
| Eleanor | 2/6 | 3/6 |
| **Total** | **8/40** | **13/40** |

## Optional lookup

| Person | Facts raw | Implications raw | Facts weighted | Implications weighted |
|---|---:|---:|---:|---:|
| Wei | 4/6 | 5/6 | 2.5 | 4.0 |
| Tomás | 4/6 | 5/6 | 2.0 | 3.0 |
| Priya | 4/6 | 5/6 | 2.0 | 2.5 |
| Devon | 3/5 | 3/5 | 1.5 | 2.5 |
| Alice | 5/6 | 4/6 | 3.0 | 2.0 |
| Hannah | 4/5 | 4/5 | 2.5 | 2.5 |
| Eleanor | 5/6 | 6/6 | 2.5 | 4.0 |
| **Total** | **29/40** | **32/40** | **16.0/40** | **20.5/40** |

A correct answer is worth 1 point without lookup and 0.5 with one or more lookups. Wrong answers are worth 0.

## Search use

| Metric | Facts | Implications |
|---|---:|---:|
| Questions with lookup | 34 | 30 |
| Total searches | 80 | 56 |
| Correct without lookup | 3 | 9 |
| Catch requests correct | 11/20 | 14/20 |
| Other questions correct | 18/20 | 18/20 |

## Caveats

This is one run. The grading was manual and not blind. The result should be repeated with new note-taking runs
and a grader that does not know which arm produced each answer.
