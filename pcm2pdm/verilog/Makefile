top = ../..
verilog_files = pcm2pdm.v

all: $(verilog_files)

pcm2pdm.v: $(top)/pcm2pdm/pcm2pdm.py $(top)/pcm2pdm/dsordn.py

%.v:
	(cd $(top); python -m pcm2pdm.pcm2pdm generate -t v) > $@

clean:
	rm -rf *.v
