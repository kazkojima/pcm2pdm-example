#!/usr/bin/env python3
#
# Copyright (c) 2022 Kaz Kojima <kkojima@rr.iij4u.or.jp>
# SPDX-License-Identifier: CERN-OHL-W-2.0

from amaranth import *
from amaranth import Signal, Module, Elaboratable

from amlib.test import GatewareTestCase, sync_test_case

import numpy as np
from math import sin, pi
from deltasigma import synthesizeNTF, realizeNTF

class FixedPointDeltaSigmaModulatorOrd5(Elaboratable):
    def __init__(self,
                 bitwidth:       int=18,
                 fraction_width: int=18,
                 osr:            int=64,
                 verbose:        bool=True) -> None:

        self.signal_in = Signal(signed(bitwidth))
        self.signal_out = Signal()
        self.strobe_in = Signal()

        order = 5
        Hinf = 1.4
        f0 = 0.
        ntf = synthesizeNTF(order, osr, 2, Hinf, f0)
        a, g, b, c = realizeNTF(ntf, 'CRFB')

        self.bitwidth = bitwidth
        self.fraction_width = fraction_width
        self.b = [int(x * 2**fraction_width) for x in b]
        self.g = [int(x * 2**fraction_width) for x in g]

    def elaborate(self, platform) -> Module:
        m = Module()

        u = self.signal_in

        bw = self.bitwidth
        fbw = self.fraction_width
        width = bw + fbw

        x = Array(Signal(signed(bw), name=f"x{i}") for i in range(5))
        # delayed x input
        dx = Array(Signal(signed(bw), name=f"dx{i}") for i in range(5))
        # delayed x
        xd = Array(Signal(signed(bw), name=f"xd{i}") for i in range(5))

        b = Array(Const(v, signed(width)) for v in self.b)
        g = Array(Const(v, signed(width)) for v in self.g)

        s = Signal(signed(bw))

        v = Signal(signed(bw))
        # dac and s must be in [-2**bw/4, 2**bw/4] to avoid integer overflow
        dac = Signal(signed(bw))

        # assume a[i] = b[i] except for i = 5
        m.d.comb += s.eq(u - dac)
        m.d.comb += self.signal_out.eq(v)
        # even: delayed integrator
        m.d.sync += [
            x[0].eq(xd[0] + dx[0]),
            x[2].eq(xd[2] + dx[2]),
            x[4].eq(xd[4] + dx[4])
        ]
        # odd: integrator with input and feedback
        m.d.sync += [
            x[1].eq(xd[1] + x[0] + ((s * b[1]) >> fbw) - ((g[0] * x[2]) >> fbw)),
            x[3].eq(xd[3] + x[2] + ((s * b[3]) >> fbw) - ((g[1] * x[4]) >> fbw)),
        ]

        with m.If(self.strobe_in):
            for i in range(5):
                m.d.sync += xd[i].eq(x[i])
            m.d.sync += [
                dx[0].eq((s * b[0]) >> fbw),
                dx[2].eq(x[1] + ((s * b[2]) >> fbw)),
                dx[4].eq(x[3] + ((s * b[4]) >> fbw))
            ]

        with m.If(u + x[4] >= 0):
            m.d.comb += dac.eq(2**(bw-2)-1)
            m.d.comb += v.eq(1)
        with m.Else():
            m.d.comb += dac.eq(-2**(bw-2)+1)
            m.d.comb += v.eq(0)

        return m

class FixedPointDeltaSigmaModulatorOrd5Test(GatewareTestCase):
    FRAGMENT_UNDER_TEST = FixedPointDeltaSigmaModulatorOrd5
    FRAGMENT_ARGUMENTS = dict(osr=32)

    @sync_test_case
    def test_dsord5(self):
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
