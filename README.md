# Personal agent memory test

This project asks a simple question:

**Should a personal assistant remember only facts, or should it also write down what those facts mean for later?**

## The problem

A personal assistant may see hundreds of emails, texts, notes, calendar events and payments. It cannot keep all of
them in a small memory file.

A plain fact can also be easy to misuse. For example:

- Fact: Fang normally works Friday mornings.
- Later fact: Fang asked for October 16 off.
- Useful memory: Fang is off October 16 -> do not schedule her that morning.

The assistant may be able to search the original phone, but it still has to know when and what to search.

## Our hypothesis

Memory notes that include useful implications will help an assistant:

1. answer more questions correctly;
2. notice more hidden conflicts before acting; and
3. search the original phone less often.

## The data

The repo contains realistic synthetic phones for seven people. Each phone has email, texts, WhatsApp, notes,
calendar events, past assistant chats, transactions and contacts.

The quiz has 40 questions:

- 20 **catch requests**, where the obvious action is wrong because of a fact somewhere else;
- 7 simple **lookups**;
- 6 questions that **combine** records; and
- 7 questions where a plan **changed**.

The questions and answer keys were written separately from the memory prompts.

## Step 1: write two memories

For every person, two fresh Kimi K2.7 Code agents read the same full phone. Both had a strict 150-word limit.

The facts agent got:

> Save whatever seems important to remember about this person.

The implications agent got the same instruction, plus:

> Where a fact has a consequence for what the person or assistant should or should not do later, write it as:
> fact -> what it implies. Only add an implication where one clearly follows.

The note-takers never saw the quiz.

## Step 2: answer without the phone

Fresh Kimi agents answered the quiz using only their 150-word memory notes. They had no tools and could not open
the phones.

- Facts memory: **8/40**
- Implications memory: **13/40**

## Step 3: answer with optional lookup

We ran every question again with a fresh agent. This made 80 quiz agents: 40 using facts notes and 40 using
implications notes.

Each agent could either:

- answer from memory; or
- search only that person's phone with a keyword.

Every file access and search was logged. No quiz agent opened another person's phone or any answer key.

## Scoring

- Correct without lookup: **1 point**
- Correct with one or more lookups: **0.5 points**
- Wrong: **0 points**

The penalty is per answer, not per search.

## Results

| Result | Facts memory | Implications memory |
|---|---:|---:|
| Raw correct | 29/40 | 32/40 |
| Weighted score | **16.0/40** | **20.5/40** |
| Catch requests correct | 11/20 | 14/20 |
| Other questions correct | 18/20 | 18/20 |
| Questions that needed lookup | 34/40 | 30/40 |
| Total searches | 80 | 56 |
| Correct without any lookup | 3 | 9 |

The two methods tied on ordinary questions. The implications notes did better on hidden catches and used fewer
searches.

## What this result means

This run supports the hypothesis, but it is not final proof. It used one note-taking run per person, only 40
questions, and manual grading that was not blind. A stronger follow-up would repeat note-taking several times and
grade shuffled answers without showing which memory produced them.

## Repo layout

- `data/`: the seven finished synthetic phones
- `questions.json`: the 40 quiz questions and answer keys
- `gen/`: phone generation and checking code
- `seeds/`: source facts used to build the phones
- `experiments/notes-run1/`: all files from this memory experiment

Inside `experiments/notes-run1/`:

- `*/facts.notes.md`: plain-fact memories
- `*/implications.notes.md`: memories with implications
- `*/*.task.md`: exact note-taking prompts
- `*/lookup/*.prompt.md`: exact lookup quiz prompts
- `lookup_results.json`: all 80 answers, searches and grades
- `no_lookup_results.json`: answers and grades without lookup
- `summary.md`: full result tables
- `score_lookup.py`: scoring script; the default lookup penalty is 0.5
