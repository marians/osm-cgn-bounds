#!/usr/bin/env python
# encoding: utf-8

import config
import os
import shapefile
import pyproj

FILES = [config.STADTBEZIRKE, config.STADTTEILE]


def convert_point_coords(p):
    global source_proj
    (lon, lat) = source_proj(p[0], p[1], inverse=True)
    return (lon, lat)

if __name__ == '__main__':
    source_proj = pyproj.Proj(config.PROJECTION)
    for filename in FILES:
        print "Shapefile:", filename
        sf = shapefile.Reader(config.SRC + os.sep + filename)
        for shape in sf.shapes():
            for point in shape.points:
                print point, convert_point_coords(point)
