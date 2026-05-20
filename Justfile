set shell := ["bash", "-uc"]

default:
    @just --list

test:
    python3 scripts/run_tests.py

alias tests := test
alias smoke := test
