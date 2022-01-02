#!/bin/bash

export GENERATE_VCDS=1

python3 -m unittest pcm2pdm.pcm2pdm.PCM2PDMTest
