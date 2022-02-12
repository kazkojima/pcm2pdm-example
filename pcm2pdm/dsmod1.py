#!/usr/bin/env python3
#
# Copyright (c) 2022 Kaz Kojima <kkojima@rr.iij4u.or.jp>
# SPDX-License-Identifier: CERN-OHL-W-2.0

from amaranth import *
from amaranth import Signal, Module, Elaboratable

from amlib.test import GatewareTestCase, sync_test_case

import numpy as np
from math import sin, pi

class FixedPointDeltaSigmaModulatorOrd1(Elaboratable):
    def __init__(self,
                 bitwidth:       int=18,
                 fraction_width: int=18,
                 osr:            int=64,
                 verbose:        bool=True) -> None:

        self.signal_in = Signal(signed(bitwidth))
        self.signal_out = Signal()
        self.strobe_in = Signal()

        self.bitwidth = bitwidth
        self.fraction_width = fraction_width

    def elaborate(self, platform) -> Module:
        m = Module()

        u = self.signal_in

        bw = self.bitwidth
        fbw = self.fraction_width
        width = bw + fbw

        x = Signal(signed(bw), name=f"x")
        # delayed x input
        dx = Signal(signed(bw), name=f"dx")
        # delayed x
        xd = Signal(signed(bw), name=f"xd")

        s = Signal(signed(bw))

        v = Signal(signed(bw))
        # dac and s must be in [-2**bw/4, 2**bw/4] to avoid integer overflow
        dac = Signal(signed(bw))

        m.d.comb += s.eq(u - dac)
        m.d.comb += self.signal_out.eq(v)
        m.d.comb += x.eq(xd + dx)

        with m.If(self.strobe_in):
            m.d.sync += xd.eq(x)
            m.d.sync += dx.eq(s)

        with m.If(u + x >= 0):
            m.d.comb += dac.eq(2**(bw-2)-1)
            m.d.comb += v.eq(1)
        with m.Else():
            m.d.comb += dac.eq(-2**(bw-2)+1)
            m.d.comb += v.eq(0)

        return m

class FixedPointDeltaSigmaModulatorOrd1Test(GatewareTestCase):
    FRAGMENT_UNDER_TEST = FixedPointDeltaSigmaModulatorOrd1
    FRAGMENT_ARGUMENTS = dict(osr=32)

    @sync_test_case
    def test_dsmod1(self):
        dut = self.dut
        N = 8192
        ftest = 0.1
        # strobe_in period = 4 clk
        u =[int(0.5*sin(2*pi*i/(4*N*ftest)) * (2**17-1)) for i in range(8192)]

        count = 0
        for i in range(N):
            yield dut.signal_in.eq(u[count])
            yield
            yield dut.strobe_in.eq(1)
            yield
            yield dut.strobe_in.eq(0)
            yield
            yield
            count = count + 1
