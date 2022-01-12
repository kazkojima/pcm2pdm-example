[> Intro
--------
Status: Trial

PCM2PDM provides a minimal PCM to PDM pipeline.

![Filter Pipeline](https://github.com/kazkojima/pcm2pdm-example/blob/main/doc/filter-pipeline.png)

The FIR lowpass filter in the pipeline is implemented with the Amaranth HDL as an [amlib](https://github.com/amaranth-community-unofficial/amlib) library. The default Delta-Sigma modulator is a 5-order CRFB modulator. Only odd order modulator is supported.

![FIR lowpass filter](https://github.com/kazkojima/pcm2pdm-example/blob/main/doc/fir-fig.png)

![Delta Sigma Modulator: NTF and Spectrum](https://github.com/kazkojima/pcm2pdm-example/blob/main/doc/deltasigma-ord5-osr48.png)

examples/gsd_butterstick.py is a running example using LiteX on Greg Davill's ButterStick board. It consumes 8 (resp. 2) multipliers when 24-bit (resp. 18-bit) width arithmetic is specified for the default 5-order modulator. One can reduce the number of required multipliers to 3 (resp. 1) by selecting order 1 delta sigma modulator with ds_order=1 in the PCM2PDM constructor, though this will impact the filter characteristics. There's also the issue of ideal tones in this order 1 modulator.
OTOH, higher order (> 5) delta-sigma modulators require higher precision calculations.

The current implementation works at 64MHz on ButterStick:
```
Max frequency for sys_clk: 85.95 MHz (PASS at 64.51 MHz)
```

To make this example work, you need to add a few lines for the PDM output pins like
```
--- a/litex_boards/platforms/gsd_butterstick.py
+++ b/litex_boards/platforms/gsd_butterstick.py
@@ -128,7 +128,14 @@ _io_r1_0 = [
         Subsignal("stp",   Pins("C8")),
         Subsignal("rst",   Pins("C9")),
         IOStandard("LVCMOS18"),Misc("SLEWRATE=FAST")
-    ), 
+    ),
+
+    # PDM output
+    ("pdmout", 0,
+        Subsignal("data", Pins("L5")),
+        Subsignal("clk", Pins("M4")),
+        IOStandard("LVCMOS33")
+    ),
 ]
 
 # Connectors ---------------------------------------------------------------------------------------
```
to the litex platform description file platform/gsd_butterstick.py.

The following code snippet added to litex bios will get 16-bit raw sound file from host with TFTP and process it to the PDM output.
```
static int last_size = 0;

unsigned int test_pdmout()
{
	unsigned int ip;
	int size;
	char *filename = "data.raw";

	printf("Get raw PCM data via TFTP\n");
	printf("Local IP : %d.%d.%d.%d\n", LOCALIP1, LOCALIP2, LOCALIP3, LOCALIP4);
	printf("Remote IP: %d.%d.%d.%d\n", REMOTEIP1, REMOTEIP2, REMOTEIP3, REMOTEIP4);

	ip = IPTOINT(REMOTEIP1, REMOTEIP2, REMOTEIP3, REMOTEIP4);
	udp_start(macadr, IPTOINT(LOCALIP1, LOCALIP2, LOCALIP3, LOCALIP4));

        if(!udp_arp_resolve(ip)) {
               printf("arp resolve fail\n");
               return -1;
	}

	size = copy_file_from_tftp_to_ram(ip, TFTP_SERVER_PORT, filename, 0x40000000);
		last_size = size;
	} else
		size = last_size;

	short *pcmdata = (void*)0x40000000;
	int i;
	for (i=0;i<size/2;i++) {
		while (*(volatile char *)CSR_PDMOUT_READY_ADDR == 0) ;
		*(volatile short *)CSR_PDMOUT_DATA_ADDR = pcmdata[i];
	}

	return 0;
}
```

[> Features
-----------
**TODO**

[> Getting started
------------------
**TODO**

PCM2PDM module is writen with Amaranth and its verilog output is needed to use it from LiteX. The command below will generate the verilog file. 
```
pushd pcm2pdm/verilog
make
popd
```

[> Tests
--------
**TODO**

[> Links
-------------

**TODO**

[1] G. Venturini, [python-deltasigma](http://www.python-deltasigma.io) and its [github repo](https://github.com/ggventurini/python-deltasigma).

See also its fork ['Add Python 3.9 & scipy 1.7.0 support'](https://github.com/Y-F-Acoustics/python-deltasigma) by Y. Fukuda.

[2] Tom Verbeure, [PDM Microphones and Sigma-Delta A/D Conversion](https://tomverbeure.github.io/2020/10/04/PDM-Microphones-and-Sigma-Delta-Conversion.html)
