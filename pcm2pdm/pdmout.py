#
# This file is part of PCM2PDM.
#
# Copyright (c) 2022 Kaz Kojima <kkojima@rr.iij4u.or.jp>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from . import data_file

class PDMout(Module, AutoCSR):
    def __init__(self, platform, pads):

        platform.add_source(data_file("pcm2pdm.v"), "verilog")
    
        self.submodules.fifo = fifo = stream.SyncFIFO([("data", 16)], 512)

        # CPU side
        self.ready = CSRStatus(1)
        self.data = CSRStorage(16)
        self.comb += [
            self.ready.status.eq(fifo.sink.ready),
            fifo.sink.data.eq(self.data.storage),
            fifo.sink.valid.eq(self.data.re),
            fifo.sink.last.eq(1),
        ]

        # PCM2PDM side
        bw = 28
        self.pcm_data = pcm_data = Signal((bw, True))
        self.pcm_strobe_in = pcm_strobe_in = Signal()
        self.pcm_ready = Signal()
        pcm_s16 = Signal((16, True))

        self.comb += [
            fifo.source.ready.eq(pcm_strobe_in),
            pcm_s16.eq(fifo.source.data),
            # scale for bit width without overflow
            # theoritically 1/4 of bw is enough, but computational errors
            # can make unexpected overflow. 3/16 will be ok
            self.pcm_data.eq((pcm_s16 + (pcm_s16 << 1)) << (bw-16-4)),
            self.pcm_ready.eq(fifo.source.valid)
        ]

        self.specials += Instance("PCM2PDM",
                                  i_clk = ClockSignal(),
                                  i_rst = ResetSignal(),
                                  i_pcm_data_in = pcm_data,
                                  o_pdm_data_out = pads.data,
                                  o_pcm_strobe_in = pcm_strobe_in,
                                  o_pdm_clock_out = pads.clk)
