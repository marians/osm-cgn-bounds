#!/usr/bin/env python
# encoding: utf-8

import shapefile
import config
import os

FILES = [config.STADTBEZIRKE, config.STADTTEILE]

if __name__ == '__main__':
    for filename in FILES:
        print "---------------------------------------------------"
        print "Shapefile:", filename
        sf = shapefile.Reader(config.SRC + os.sep + filename)
        shapes = sf.shapes()
        #print "Felder:", sf.fields
        print "Anzahl Shapes: %d" % len(shapes)

        numpoints = 0
        for shape in shapes:
            numpoints += len(shape.points)
        print "Anzahl Punkte: %d" % numpoints
        print "Anzahl Punkte/Shape (Mittel): %.1f" % (numpoints / len(shapes))
        print ""
        print "Shapes:"
        sr = sf.shapeRecords()
        for n in range(0, len(shapes)):
            sr_test = sr[n]
            print (n + 1), sr_test.record[2], ', Punkte:', len(shapes[n].points)
