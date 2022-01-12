#!/usr/bin/env python3
#
# Copyright (c) 2021 Kaz Kojima <kkojima@rr.iij4u.or.jp>
# SPDX-License-Identifier: CERN-OHL-W-2.0

from amaranth import *
from amaranth.lib.fifo import SyncFIFO
from amaranth.hdl.ast import Rose, Fell
from amaranth.cli import main

from amlib.test import GatewareTestCase, sync_test_case
from amlib.utils import SimpleClockDivider
from amlib.dsp import FixedPointFIRFilter

from pcm2pdm.dsord1 import FixedPointDeltaSigmaModulatorOrd1
from pcm2pdm.dsordn import FixedPointDeltaSigmaModulator

import numpy as np
from math import sin, pi

class PCM2PDM(Elaboratable):
    """ PCM to PDM filter pipeline

        Attributes
        ----------
        pdm_clock_out: Signal(), output
            PDM clock signal
        pdm_data_out: Signal(), output
            PDM data signal
        pcm_strobe_in: Signal(), output
            PCM clock signal
        pcm_data_in: Signal(16), input
            PCM data signal

        Parameters
        ----------
        divisor: int
            clock divisor constant
        bitwidth: int
            width
        fraction_width: int
            fraction width
        fs: int
            sampling frequency
        pre_upsample: int
            upsample before filter
        post_upsample: int
            upsample after filter
        fir_order: int
            fir filter order
        fir_cutoff: int or list
            fir filter cutoff frequency or pass/stop start frequencies
        fir_weight: list
            fir filter ripple/attenuation when pass/stop list is specified
        ds_order: int
            deltasigma modulator order
        """
    def __init__(self,
                 divisor: int=28,
                 bitwidth: int=24,
                 fraction_width: int=24,
                 fs: int=48000,
                 pre_upsample: int=4,
                 post_upsample: int=12,
                 fir_order: int=179,
                 fir_cutoff: list=[10000, 14000],
                 fir_weight: list=[0.05, 60],
                 ds_order: int=5):
        self.pdm_clock_out = Signal()
        self.pdm_data_out = Signal()
        self.pcm_strobe_in = Signal()
        self.pcm_data_in = Signal(signed(bitwidth))

        self.divisor = divisor
        self.bitwidth = bitwidth
        self.fraction_width = fraction_width
        assert bitwidth <= fraction_width, f"Bitwidth {bitwidth} must not exceed {fraction_width}"
        self.pre_upsample = pre_upsample
        self.post_upsample = post_upsample
        self.fs = fs
        self.fir_order = fir_order
        self.fir_cutoff = fir_cutoff
        self.fir_weight = fir_weight
        self.ds_order = ds_order

    def elaborate(self, platform) -> Module:
        m = Module()

        clk_divider = SimpleClockDivider(self.divisor)
        m.submodules.clk_divider = clk_divider
        m.d.comb += [
            clk_divider.clock_enable_in.eq(1),
            self.pdm_clock_out.eq(~clk_divider.clock_out)
        ]
        strobe = Rose(clk_divider.clock_out, domain="sync")

        bw = self.bitwidth
        fbw = self.fraction_width
        osr = self.pre_upsample * self.post_upsample

        # Strobe pulses
        count1 = Signal(range(self.post_upsample))
        count2 = Signal(range(osr))
        strobe0 = Signal() # for delta sigma
        strobe1 = Signal() # for fir filter
        strobe2 = Signal() # for pcm input
        with m.If(strobe):
            with m.If(count1 == 0):
                m.d.sync += count1.eq(self.post_upsample - 1)
            with m.Else():
                m.d.sync += count1.eq(count1 - 1)
            with m.If(count2 == 0):
                m.d.sync += count2.eq(osr - 1)
            with m.Else():
                m.d.sync += count2.eq(count2 - 1)
            m.d.sync += [
                strobe0.eq(1),
                strobe1.eq(count1 == 0),
                strobe2.eq(count2 == 0)
            ]
        with m.Else():
            m.d.sync += [
                strobe0.eq(0),
                strobe1.eq(0),
                strobe2.eq(0)
            ]

        # filters
        fir_fs = self.fs * self.pre_upsample
        fir = FixedPointFIRFilter(samplerate=fir_fs,
                                  bitwidth=bw,
                                  fraction_width=fbw,
                                  cutoff_freq=self.fir_cutoff,
                                  filter_order=self.fir_order,
                                  weight=self.fir_weight,
                                  mac_loop=True,
                                  verbose=False)
        m.submodules.fir = fir

        if self.ds_order==1:
            ds = FixedPointDeltaSigmaModulatorOrd1(bitwidth=bw,
                                                   fraction_width=fbw,
                                                   osr=osr,
                                                   verbose=False)
        else:
            ds = FixedPointDeltaSigmaModulator(bitwidth=bw,
                                               fraction_width=fbw,
                                               order=self.ds_order,
                                               osr=osr,
                                               mul_loop=True,
                                               verbose=False)
        m.submodules.ds = ds
            
        with m.If(strobe2):
            m.d.comb += fir.signal_in.eq(self.pcm_data_in)
        m.d.comb += ds.signal_in.eq(fir.signal_out * self.pre_upsample)

        m.d.comb += [
            self.pcm_strobe_in.eq(strobe2),
            fir.enable_in.eq(strobe1),
            ds.strobe_in.eq(strobe0),
            self.pdm_data_out.eq(ds.signal_out)
        ]

        return m

class PCM2PDMTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = PCM2PDM
    FRAGMENT_ARGUMENTS = dict(divisor=28, bitwidth=18, fraction_width=18)

    @sync_test_case
    def test_pcm2pdm(self):
        dut = self.dut
        N = 512
        ftest = 0.1
        u =[int(0.5*sin(2*pi*i/(4*N*ftest)) * (2**16-7)) for i in range(N)]

        osr = 48
        divisor = 28
        
        count = 0
        for i in range(N):
            yield dut.pcm_data_in.eq(u[count])
            yield
            for _ in range(osr*divisor-1):
                yield
            count = count + 1

 
if __name__ == "__main__":

    pcm2pdm = PCM2PDM()

    ports = [
        pcm2pdm.pcm_data_in,
        pcm2pdm.pcm_strobe_in,
        pcm2pdm.pdm_data_out,
        pcm2pdm.pdm_clock_out,
    ]
    main(pcm2pdm, name="PCM2PDM", ports=ports)
