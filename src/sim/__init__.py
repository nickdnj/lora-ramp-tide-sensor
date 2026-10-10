"""Offline simulator for the LoRa ramp tide sensor.

A synthetic world (tide, ramp, inclinometer, node power, lossy radio, fake NOAA)
on a virtual clock, feeding the real tidesvc ingest pipeline through a fake
radio source. This package may import tidesvc; tidesvc must never import it.
"""
