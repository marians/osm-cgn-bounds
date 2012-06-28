#!/usr/bin/env python
# encoding: utf-8

"""
Dieses Script bereitet den Export der Grenzdaten
als OpenStreetmap Datei vor.

Die Vorgehensweise:
- Die Stadtteil-Shapes werden eingelesen
- Die Punkte der Stadtteil-Shapes werden gespeichert
- Ein Dict speichert je Punkt die Information, welche Grenzen
  diesen Punkt nutzen. So können gemeinsam genutzte Punkte
  identifiziert werden.
- Die Shape-Grenzen werden der Reihe nach verarbeitet. Es werden
  die kleinstmöglichen Teilstücke der Grenzen gebildet, indem
  jeweils die Verbindungen zwischen einem und dem nächsten
  Grenzpunkt als Weg abgelegt werden. Dabei wird darauf geachtet,
  dass jedes Teilstück nur einmal vorhanden ist.
- Die Wege werden iterativ paarweise zusammengefügt, an Stellen,
  wo exakt zwei Wege zusammen laufen, bis keine solchen Stellen
  mehr zu finden sind.
- Es wird eine rudimentäre SVG-Grafik als Vorschau erstellt

Das klappt soweit ganz gut. Leider werden noch nicht alle möglichen
Teilwege miteinander verbunden.

"""

import config
import os
import sys
import shapefile
import pyproj

FILES = [config.STADTBEZIRKE, config.STADTTEILE]


def convert_point_coords(p):
    global source_proj
    (lon, lat) = source_proj(p[0], p[1], inverse=True)
    return (lon, lat)


def point_id(point):
    """Erstellt ID-String aus Float-Tupel"""
    return "%.15f|%.15f" % point


def read_shapes(path, level, points, shapes):
    """
    Liest shapes und Punkte in die interne Datenstruktur ein.
    Punkte sind Koordinaten plus Meta-Daten. Shapes sind die
    Abfolge von Punkte plus Meta-Daten."""
    print "Shapefile:", config.STADTTEILE
    sf = shapefile.Reader(path)
    sr = sf.shapeRecords()
    this_shapes = sf.shapes()
    for n in range(0, len(this_shapes)):
        shape_records = sr[n]
        stadtteil = None
        stadtbezirk = None
        if level == 'STADTTEIL':
            stadtteil = shape_records.record[2]
            stadtbezirk = shape_records.record[5]
        else:
            stadtbezirk = shape_records.record[2]
        # store shape
        shape_id = level + '_' + str(n)
        if stadtteil is not None:
            shapes[shape_id] = {
                'level': level,
                'stadtbezirk': stadtbezirk,
                'stadtteil': stadtteil,
                'points': []
            }
        else:
            shapes[shape_id] = {
                'level': level,
                'stadtbezirk': stadtbezirk,
                'stadtteil': stadtteil,
                'points': []
            }
        # store points
        for point in this_shapes[n].points:
            (lon, lat) = convert_point_coords(point)
            pid = point_id((lon, lat))
            shapes[shape_id]['points'].append(pid)
            if pid not in points:
                points[pid] = {
                    'lon': lon,
                    'lat': lat,
                    'references': []
                }
            if stadtteil is not None:
                points[pid]['references'].append({
                    'shape_id': level + '_' + str(n),
                    'level': level,
                    'stadtbezirk': stadtbezirk,
                    'stadtteil': stadtteil
                })
            else:
                points[pid]['references'].append({
                    'shape_id': n,
                    'level': level,
                    'stadtbezirk': stadtbezirk
                })
    return (points, shapes)


def way_exists(point1, point2, ways):
    """Gibt True zurück, falls ein Weg zwischen diesen Punkten
    existiert"""
    if point1 in ways:
        if point2 in ways[point1]:
            return True
    if point2 in ways:
        if point1 in ways[point2]:
            return True
    return False


def append_way(ways, point1, point2, way):
    """
    Fügt den Weg in das Wege-Dict ein, so dass
    Start- und Enpunkt in reproduzierbarer Reihenfolge
    stehen - falls noch nicht vorhanden.
    """
    points = sorted([point1, point2])
    if points[0] not in ways:
        ways[points[0]] = {}
    if points[1] not in ways[points[0]]:
        ways[points[0]][points[1]] = way
    else:
        ways[points[0]][points[1]]['shapes'].append(way['shapes'][0])
    return (points[0], points[1], ways)


def make_ways(points, shapes, ways):
    """Erstellt Nicht-redundante minimale Wege aus den gegebenen Shapes.
    Das Wege-Dict ist zweidimensional, sodass jeweils Anfangs- und Endpunkt-ID
    einen Schlüssel bilden."""
    for shape_id in shapes:
        #print "Shape Start --------------------------------------------"
        # Teste, ob Shape geschlossen ist
        point_ids = shapes[shape_id]['points']
        if point_ids[0] != point_ids[-1]:
            # TODO: Ggf. ersten Punkt als letzten anhängen
            print "Shape", shape_id, "ist nicht geschlossen!"
        waypoints = []
        for point_id in point_ids:
            #print "Aktueller Punkt:", points[point_id]['lon'], points[point_id]['lat']
            # Überspringen, falls identisch mit vorigem Punkt
            if len(waypoints) > 0 and point_id == waypoints[-1]:
                continue
            waypoints.append(point_id)
            if len(waypoints) == 2:
                (start, end, ways) = append_way(ways, waypoints[-1], waypoints[0], {
                    'points': waypoints,
                    'shapes': [shape_id]
                })
                # Aktueller Endpunkt ist der erste Punkt des nächsten Ways
                waypoints = [point_id]
    return ways


def count_ways(ways):
    count = 0
    for point1 in ways:
        for point2 in ways[point1]:
            count += 1
    return count


def get_ways_to_point(ways, point):
    """
    Gibt die Punkt-Paare zurück, zu denen Wege von diesem
    Punkt aus führen
    """
    point_pairs = []
    for p1 in ways:
        for p2 in ways[p1]:
            if p1 == point or p2 == point:
                point_pairs.append((p1, p2))
    return point_pairs


def count_ways_to_point(ways, point):
    """
    Zählt die Wege, die an einem bestimmten Punkt
    anfangen oder enden
    """
    return len(get_ways_to_point(ways, point))


def delete_way(ways, point_tuple):
    (p1, p2) = point_tuple
    p = sorted([p1, p2])
    del ways[p[0]][p[1]]
    if len(ways[p[0]]) == 0:
        del ways[p[0]]
    return ways


def merge_ways(point_tuples, ways):
    """
    Fügt zwei Wege, gekennzeichnet durch je ein Punkt-Tupel,
    zu einem zusammen
    """
    (w1, w2) = point_tuples
    w1points = ways[w1[0]][w1[1]]['points']
    w2points = ways[w2[0]][w2[1]]['points']

    # Test: Shape-Metadaten beider Wege müssen identisch sein
    shapes1 = sorted(ways[w1[0]][w1[1]]['shapes'])
    shapes2 = sorted(ways[w2[0]][w2[1]]['shapes'])
    if shapes1 != shapes2:
        print "FEHLER: Wege haben ungleiche Shape-Listen:"
        print "Weg1: ", shapes1
        print "Weg2: ", shapes2

    # Erst neue Wegpunkt-Liste erstellen.
    # Dazu herausfinden, in welcher Reihenfolge die Wege zusammen gehören
    # TODO Sonderfall: Zwei Wege können an zwei Stellen zusammenstoßen

    # Test: Wegpunkte beider Wege müssen mindestens 2 Elemente lang sein
    if len(w1points) < 2:
        print "FEHLER: Weg 1 hat zu wenig Punkte."
        print ways[w1[0]][w1[1]]
        return ways
    if len(w2points) < 2:
        print "FEHLER: Weg 2 hat zu wenig Punkte."
        print ways[w2[0]][w2[1]]
        return ways

    waypoints = []
    if w1points[-1] == w2points[0]:
        # w2 folgt auf w1
        waypoints.extend(w1points)
        waypoints.extend(w2points[1:])
    elif w2points[-1] == w1points[0]:
        # w1 folgt auf w2
        waypoints.extend(w2points)
        waypoints.extend(w1points[1:])
    elif w1points[-1] == w2points[-1]:
        # w2 folgt in umgekehrter Punktfolge auf w1
        waypoints.extend(w1points)
        w2pointsr = w2points
        w2pointsr.reverse()
        waypoints.extend(w2pointsr[1:])
    elif w1points[0] == w2points[0]:
        # w2 folgt auf w1 (w1 in umgekehrter Reihenfolge)
        w1pointsr = w1points
        w1pointsr.reverse()
        waypoints.extend(w1pointsr)
        waypoints.extend(w2points[1:])
    else:
        print "FEHLER: Die Wege haben keinen gemeinsamen Endpunkt."
        print ways[w1[0]][w1[1]]
        print ways[w2[0]][w2[1]]
        sys.exit()
        return ways
    #print "Neue Punktfolge:", waypoints

    # Alte Punkte entfernen
    ways = delete_way(ways, w1)
    ways = delete_way(ways, w2)
    (start, end, ways) = append_way(ways, waypoints[0], waypoints[-1], {
        'points': waypoints,
        'shapes': shapes1
    })
    return ways


def iterate_merge_ways(ways, points):
    itercount = 0
    while True:
        num_ways = count_ways(ways)
        itercount += 1
        print "Wege zusammenfügen: Iteration", itercount, ", Wege vorher:", num_ways
        for start_point_id in points:
            if start_point_id in ways:
                ways_here = get_ways_to_point(ways, start_point_id)
                if len(ways_here) == 2:
                    # Hier treffen sich zwei Wege.
                    #print start_point_id, "- Wege werden zusammengefügt"
                    #print ways_here
                    ways = merge_ways(ways_here, ways)
                    continue
                #else:
                #    print "Hier gehen", num_ways_here, "Wege ab"
        if num_ways == count_ways(ways):
            # Es ist keine Optimierung mehr erfolgt - also Ende
            break
    return ways


def draw_ways_svg(ways, points, outfile):
    svg = open(outfile, 'w')
    svg.write('<?xml version="1.0" encoding="utf-8" ?>' + "\n")
    svg.write('<svg xmlns="http://www.w3.org/2000/svg" version="1.1">' + "\n")
    for p1 in ways:
        for p2 in ways[p1]:
            way = ways[p1][p2]
            mypoints = []
            for point_id in way['points']:
                mypoints.append(str(points[point_id]['lon'] * 10) + ',' + str(points[point_id]['lat'] * 10))
            svg.write('<polyline points="' + (' '.join(mypoints)) + '" />' + "\n")
    svg.write('</svg>' + "\n")


if __name__ == '__main__':
    source_proj = pyproj.Proj(config.PROJECTION)
    points = {}
    shapes = {}
    ways = {}
    (points, shapes) = read_shapes(
        config.SRC + os.sep + config.STADTTEILE,
        "STADTTEIL", points, shapes)
    ways = make_ways(points, shapes, ways)
    print len(points), "Punkte"
    ways = iterate_merge_ways(ways, points)
    print count_ways(ways), "Wege nachher"
    draw_ways_svg(ways, points, 'ways_preview.svg')
