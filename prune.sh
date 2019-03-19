#!/bin/bash
tail -n 10000 gerrit_reviewer_bot.out > out.tmp
mv out.tmp gerrit_reviewer_bot.out

tail -n 10000 gerrit_reviewer_bot.err > err.tmp
mv err.tmp gerrit_reviewer_bot.err
