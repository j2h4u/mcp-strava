set shell := ["bash", "-uc"]

default:
    @just --list

test:
    python3 -m pytest

alias tests := test
alias smoke := test
