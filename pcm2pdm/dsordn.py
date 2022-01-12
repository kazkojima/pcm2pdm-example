#!/usr/bin/env python3
#
# Copyright (c) 2022 Kaz Kojima <kkojima@rr.iij4u.or.jp>
# SPDX-License-Identifier: CERN-OHL-W-2.0

from amaranth import *
from amaranth import Signal, Module, Elaboratable

from amlib.test import GatewareTestCase, sync_test_case

import numpy as np
from math import sin, pi
from pprint import pformat
from deltasigma import synthesizeNTF, realizeNTF

class FixedPointDeltaSigmaModulator(Elaboratable):
    def __init__(self,
                 bitwidth:       int=18,
                 fraction_width: int=18,
                 order:          int=5,
                 osr:            int=64,
                 hinf:           float=1.5,
                 f0:             float=0.,
                 mul_loop:       bool=False,
                 verbose:        bool=True) -> None:

        self.signal_in = Signal(signed(bitwidth))
        self.signal_out = Signal()
        self.strobe_in = Signal()

        assert order % 2 == 1 and order > 1, f"only odd order > 1 is supported"
        self.order = order

        ntf = synthesizeNTF(order, osr, 2, hinf, f0)
        a, g, b, c = realizeNTF(ntf, 'CRFB')

        self.bitwidth = bitwidth
        self.fraction_width = fraction_width
        assert bitwidth <= fraction_width, f"Bitwidth {bitwidth} must not exceed  {fraction_width}"
        self.b = [int(x * 2**fraction_width) for x in b]
        if order > 3:
            self.g = [int(-x * 2**fraction_width) for x in g]
        elif order == 3:
            self.g = [int(-g * 2**fraction_width)]

        self.mul_loop = mul_loop

        if verbose:
            print(f"deltasigma CRFB order {order} osr {osr} Hinf {hinf} f0 {f0}")
            print(f"a: {pformat(a)}")
            print(f"g: {pformat(g)}")
            print(f"b: {pformat(b)}")
            print(f"c: {pformat(c)}")
            print(f"fixed b:{self.b}")
            print(f"fixed g:{self.g}")

    def elaborate(self, platform) -> Module:
        m = Module()

        u = self.signal_in

        bw = self.bitwidth
        fbw = self.fraction_width
        # one more bit is needed for signed mult >> shift
        width = max(bw, fbw) + 1
        n = self.order

        x = Array(Signal(signed(bw), name=f"x{i}") for i in range(n))
        # delayed x input
        dx = Array(Signal(signed(bw), name=f"dx{i}") for i in range(n))
        # delayed x
        xd = Array(Signal(signed(bw), name=f"xd{i}") for i in range(n))

        b = Array(Const(v, signed(width)) for v in self.b)
        g = Array(Const(v, signed(width)) for v in self.g)

        s = Signal(signed(bw))

        v = Signal(signed(bw))
        # dac and s must be in [-2**bw/4, 2**bw/4] to avoid integer overflow
        dac = Signal(signed(bw))

        # weighted sum and feedback
        ws = Array(Signal(signed(bw), name=f"ws{i}") for i in range(n))
        fb = Array(Signal(signed(bw), name=f"fb{i}") for i in range(n//2))

        mul_loop = self.mul_loop
        if mul_loop:
            ix = Signal(range(n+1))
            ma = Signal(signed(width))
            mb = Signal(signed(width))
            mz = Signal(signed(width))
            m.d.comb += mz.eq((ma * mb) >> fbw),

        m.d.comb += self.signal_out.eq(v)

        with m.FSM(reset="IDLE"):
            with m.State("IDLE"):
                with m.If(self.strobe_in):
                    for i in range(n):
                        m.d.sync += xd[i].eq(x[i])
                    m.d.sync += dx[0].eq(ws[0])
                    for i in range(n//2):
                        m.d.sync += dx[2*i+2].eq(x[2*i+1] + ws[2*i+2])
                    m.next = "EVEN"

            with m.State("EVEN"):
                # even: delayed integrator
                for i in range(n//2+1):
                    m.d.sync += x[2*i].eq(xd[2*i] + dx[2*i])
                m.next = "DACK"

            with m.State("DACK"):
                # assume a[i] = b[i] except for i = n
                m.d.sync += s.eq(u - dac)
                if mul_loop:
                    m.d.sync += [
                        ix.eq(0),
                        ma.eq(g[0]),
                        mb.eq(x[2])
                    ]
                    m.next = "MULT_FB"
                else:
                    m.next = "MULT"

            if mul_loop:
                with m.State("MULT_FB"):
                    with m.If(ix == n//2-1):
                        m.d.sync += [
                            fb[ix].eq(mz),
                            ma.eq(b[0]),
                            mb.eq(s),
                            ix.eq(0)
                        ]
                        m.next = "MULT_WS"
                    with m.Else():
                        m.d.sync += [
                            fb[ix].eq(mz),
                            ma.eq(g[ix+1]),
                            mb.eq(x[2*ix+4]),
                            ix.eq(ix+1)
                        ]

                with m.State("MULT_WS"):
                    with m.If(ix == n-1):
                        m.d.sync += ws[ix].eq(mz)
                        m.next = "ODD"
                    with m.Else():
                        m.d.sync += [
                            ws[ix].eq(mz),
                            ma.eq(b[ix+1]),
                            # mb.eq(s),
                            ix.eq(ix+1)
                        ]

            else:
                with m.State("MULT"):
                    for i in range(n):
                        m.d.sync += ws[i].eq((b[i] * s) >> fbw)
                    for i in range(n//2):
                        m.d.sync += fb[i].eq((g[i] * x[2*i+2]) >> fbw)
                    m.next = "ODD"

            with m.State("ODD"):
                # odd: integrator with input and feedback
                for i in range(n//2):
                    m.d.sync += x[2*i+1].eq(xd[2*i+1] + x[2*i] + ws[2*i+1] + fb[i])
                m.next = "IDLE"

        with m.If(u + x[n-1] >= 0):
            m.d.comb += dac.eq(2**(bw-2)-1)
            m.d.comb += v.eq(1)
        with m.Else():
            m.d.comb += dac.eq(-2**(bw-2)+1)
            m.d.comb += v.eq(0)

        return m

class FixedPointDeltaSigmaModulatorTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = FixedPointDeltaSigmaModulator
    FRAGMENT_ARGUMENTS = dict(osr=32, mul_loop=True)

    @sync_test_case
    def test_dsordn(self):
        dut = self.dut
        N = 8192
        ftest = 0.1
        # strobe_in period = 28 clk
        u =[int(0.5*sin(2*pi*i/(28*N*ftest)) * (2**17-1)) for i in range(8192)]

        count = 0
        for i in range(N):
            yield dut.signal_in.eq(u[count])
            yield
            yield dut.strobe_in.eq(1)
            yield
            yield dut.strobe_in.eq(0)
            yield
            for _ in range(28-3):
                yield
            count = count + 1
