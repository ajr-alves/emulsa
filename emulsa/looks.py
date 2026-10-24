"""The built-in looks.

Each look starts from a Sony in-camera recipe published by Recipe Lab v1.7.0
(https://github.com/voxivoid/recipe-lab-sony-pmca/tree/v1.7.0, MIT licence, (c) Andre Domingues). Only
that MIT release is used; later Recipe Lab releases are GPL-3.0. The recipe sets Creative Style,
saturation, contrast, white balance, DRO, exposure and Picture Effect. ``recipe_params`` turns those
camera settings into engine parameters, and ``CHARACTER`` adds what a camera setting cannot express
(split toning, per-hue shifts, faded blacks, grain), which is where most of a film stock's feel lives.
"""
from __future__ import annotations

import copy
import re

# brand, name, Creative Style, saturation, contrast, sharpness, white balance, A/B, G/M, EV (1/3 stops), DRO (0 off, 1-5, 6 auto), Picture Effect
RECIPES = [
    ('Sony'                , 'FACTORY (ST)'                        , 'Standard'     ,  0,  0,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Sony'                , 'Sony PT (portrait)'                  , 'Portrait'     ,  0,  0,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Sony'                , 'Sony NT (neutral)'                   , 'Neutral'      ,  0,  0,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Sony'                , 'Sony VV (vivid)'                     , 'Vivid'        ,  0,  0,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Sony'                , 'Sony VV2'                            , 'Vivid'        ,  2,  1,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Sony'                , 'Sony FL (film-like)'                 , 'Neutral'      , -3, -1,  0, 'AWB'  ,  1,  0,  0, 6, None),
    ('Sony'                , 'Sony IN (instant)'                   , 'Neutral'      , -3, -3,  0, 'AWB'  ,  0, -1,  0, 6, None),
    ('Sony'                , 'Sony SH (soft high-key)'             , 'Light'        , -2, -2,  0, 'AWB'  ,  1,  0,  3, 6, 'Soft High-key'),
    ('Fuji simulations'    , 'Provia'                              , 'Standard'     ,  1,  0,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Fuji simulations'    , 'Velvia'                              , 'Vivid'        ,  3,  2,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Fuji simulations'    , 'Astia'                               , 'Portrait'     ,  0, -1,  0, 'AWB'  ,  1,  0,  1, 6, None),
    ('Fuji simulations'    , 'Classic Chrome'                      , 'Standard'     , -1,  2,  0, 'AWB'  ,  3,  1, -1, 6, None),
    ('Fuji simulations'    , 'Classic Negative'                    , 'Standard'     , -3,  3,  1, 'AWB'  , -1,  1,  0, 6, None),
    ('Fuji simulations'    , 'Nostalgic Neg'                       , 'Standard'     ,  1,  0,  0, 'AWB'  ,  3,  0,  0, 6, None),
    ('Fuji simulations'    , 'Reala Ace'                           , 'Standard'     ,  0,  1,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Fuji simulations'    , 'Pro Neg Std'                         , 'Portrait'     , -2, -1,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Fuji simulations'    , 'Pro Neg Hi'                          , 'Portrait'     , -2,  1,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Fuji simulations'    , 'Eterna'                              , 'Neutral'      , -3, -2, -1, 'AWB'  ,  0,  0, -1, 3, None),
    ('Fuji simulations'    , 'Eterna Bleach Bypass'                , 'Neutral'      , -3,  3,  0, 'AWB'  ,  0,  0, -1, 0, None),
    ('Fuji simulations'    , 'Acros'                               , 'Black & White',  0,  1,  1, 'AWB'  ,  0,  0,  0, 6, None),
    ('Fuji simulations'    , 'Acros +Ye (yellow filter)'           , 'Black & White',  0,  1,  1, '4000K',  0,  0,  0, 6, None),
    ('Fuji simulations'    , 'Acros +R (red filter)'               , 'Black & White',  0,  0,  0, '2500K',  0,  0,  0, 6, 'High Contrast Mono'),
    ('Fuji simulations'    , 'Acros +G (green filter)'             , 'Black & White',  0,  1,  1, '5600K',  0,  4,  0, 6, None),
    ('Fuji simulations'    , 'Sepia'                               , 'Sepia'        ,  0,  0,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Fuji film'           , 'Fuji Pro 400H'                       , 'Light'        , -2, -2,  0, 'AWB'  , -1,  1,  2, 6, None),
    ('Fuji film'           , 'Fuji Fortia 50'                      , 'Vivid'        ,  3,  2,  0, 'AWB'  , -1,  0, -1, 6, None),
    ('Fuji film'           , 'Fuji Superia 400'                    , 'Standard'     ,  1,  1,  0, 'AWB'  ,  1,  1,  1, 6, None),
    ('Fuji film'           , 'Fuji C200'                           , 'Standard'     ,  0,  0,  0, 'AWB'  , -1,  1,  0, 6, None),
    ('Fuji film'           , 'Fuji Natura 1600'                    , 'Portrait'     , -2, -2,  0, 'AWB'  ,  1,  0,  1, 6, None),
    ('Kodak'               , 'Kodak Portra 160'                    , 'Portrait'     , -3, -2,  0, 'AWB'  ,  1, -1,  2, 6, None),
    ('Kodak'               , 'Kodak Portra 400'                    , 'Portrait'     , -1, -1,  0, 'AWB'  ,  3,  1,  2, 6, None),
    ('Kodak'               , 'Kodak Portra 800'                    , 'Portrait'     , -2, -2,  0, 'AWB'  ,  1,  1,  1, 6, None),
    ('Kodak'               , 'Kodak Gold 200'                      , 'Standard'     ,  2,  1,  0, 'AWB'  ,  3,  1,  1, 6, None),
    ('Kodak'               , 'Kodak Ultra Max 400'                 , 'Standard'     ,  0,  0,  0, 'AWB'  ,  0,  1,  1, 6, None),
    ('Kodak'               , 'Kodak Color Plus 200'                , 'Standard'     ,  1,  1,  0, 'AWB'  ,  2,  1,  1, 6, None),
    ('Kodak'               , 'Kodak Ektar 100'                     , 'Standard'     ,  3,  1,  1, 'AWB'  ,  0,  0, -1, 6, None),
    ('Kodak'               , 'Kodak Ektachrome E100'               , 'Clear'        ,  3,  1,  0, 'AWB'  , -1,  0, -1, 6, None),
    ('Kodak'               , 'Kodachrome 64'                       , 'Deep'         ,  3,  2,  1, 'AWB'  , -1,  0, -1, 6, None),
    ('Kodak'               , 'Kodak Vision3 500T (daylight)'       , 'Neutral'      , -1,  0,  0, '3200K',  0,  0,  1, 3, None),
    ('Kodak'               , 'Kodak Vision 200T (Asteroid City)'   , 'Neutral'      , -2, -3,  0, '5000K',  2,  3,  1, 3, None),
    ('Kodak'               , 'Kodak Tri-X 400'                     , 'Black & White',  0,  2,  2, 'AWB'  ,  0,  0,  1, 6, None),
    ('Kodak'               , 'Kodak T-Max'                         , 'Black & White',  0,  2,  3, 'AWB'  ,  0,  0,  0, 6, None),
    ('Kodak'               , 'Kodak Tri-X 1600 (pushed)'           , 'Black & White',  0,  0,  0, 'AWB'  ,  0,  0,  1, 6, 'High Contrast Mono'),
    ('Cine'                , 'Cinestill 50D (Blue Velvet)'         , 'Standard'     , -2, -1,  0, '5500K', -1, -1,  0, 6, None),
    ('Cine'                , 'Cinestill 800T'                      , 'Neutral'      ,  0,  0,  0, '3200K',  0, -1,  1, 6, None),
    ('Cine'                , 'Classic Cinema'                      , 'Standard'     ,  0, -1,  0, '6000K',  2,  0,  0, 3, None),
    ('Cine'                , 'Rec709 Video (flat-ish)'             , 'Neutral'      , -2, -2,  0, 'AWB'  ,  0,  0,  0, 5, None),
    ('Ricoh GR'            , 'GR Positive Film'                    , 'Standard'     ,  3,  2,  0, 'AWB'  ,  2,  0, -1, 6, None),
    ('Ricoh GR'            , 'GR Negative Film'                    , 'Neutral'      , -2,  1,  0, 'AWB'  , -1,  1,  1, 6, None),
    ('Ricoh GR'            , 'GR Bleach Bypass'                    , 'Neutral'      , -3,  3,  1, 'AWB'  ,  0,  0,  0, 0, None),
    ('Ricoh GR'            , 'GR Retro'                            , 'Standard'     , -3, -1,  0, 'AWB'  ,  3, -1,  0, 6, 'Retro Photo'),
    ('Ricoh GR'            , 'GR Cross Process'                    , 'Vivid'        ,  2,  2,  0, 'AWB'  , -2,  4,  0, 6, None),
    ('Ricoh GR'            , 'GR Hi-Contrast B&W'                  , 'Black & White',  0,  3,  1, 'AWB'  ,  0,  0,  0, 6, 'High Contrast Mono'),
    ('Ricoh GR'            , 'GR Hard Monotone'                    , 'Black & White',  0,  2,  2, 'AWB'  ,  0,  0,  0, 6, None),
    ('Ricoh GR'            , 'GR Soft Monotone'                    , 'Black & White',  0, -2, -1, 'AWB'  ,  0,  0,  0, 6, None),
    ('Leica'               , 'Leica Contemporary'                  , 'Standard'     ,  1,  1,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Leica'               , 'Leica Classic'                       , 'Standard'     , -1,  2,  0, 'AWB'  ,  1,  0,  0, 6, None),
    ('Leica'               , 'Leica Eternal'                       , 'Neutral'      , -3, -1,  0, 'AWB'  ,  1,  0,  0, 3, None),
    ('Leica'               , 'Leica Monochrom'                     , 'Black & White',  0,  2,  1, 'AWB'  ,  0,  0,  0, 6, None),
    ('Hasselblad'          , 'Hasselblad HNCS Natural'             , 'Neutral'      , -1, -1,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Canon / Nikon'       , 'Canon Standard'                      , 'Standard'     ,  1,  1,  0, 'AWB'  ,  1, -1,  0, 6, None),
    ('Canon / Nikon'       , 'Canon Portrait'                      , 'Portrait'     ,  0,  0, -1, 'AWB'  ,  1, -1,  0, 6, None),
    ('Canon / Nikon'       , 'Canon Faithful'                      , 'Neutral'      ,  0,  0,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Canon / Nikon'       , 'Nikon Flat'                          , 'Neutral'      , -3, -3, -1, 'AWB'  ,  0,  0,  0, 5, None),
    ('Canon / Nikon'       , 'Nikon Vivid'                         , 'Vivid'        ,  1,  1,  1, 'AWB'  ,  0,  0,  0, 6, None),
    ('Panasonic / Olympus' , 'Pana L.Monochrome D'                 , 'Black & White',  0,  3,  1, 'AWB'  ,  0,  0,  0, 6, None),
    ('Panasonic / Olympus' , 'Pana L.ClassicNeo'                   , 'Neutral'      , -3, -1,  0, 'AWB'  ,  2,  0,  1, 6, None),
    ('Panasonic / Olympus' , 'Olympus Pop Art'                     , 'Vivid'        ,  3,  3,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Panasonic / Olympus' , 'Olympus Pale & Light'                , 'Light'        , -3, -2,  0, 'AWB'  ,  0,  0,  2, 6, None),
    ('Other stocks'        , 'Agfa Vista 200'                      , 'Standard'     ,  2,  1,  0, 'AWB'  ,  2, -1,  1, 6, None),
    ('Other stocks'        , 'Agfa Ultra 100'                      , 'Vivid'        ,  3,  1,  0, 'AWB'  ,  0,  0,  0, 6, None),
    ('Other stocks'        , 'Polaroid / Instax'                   , 'Standard'     , -3, -2,  0, 'AWB'  ,  1, -2,  1, 6, 'Retro Photo'),
    ('Ilford'              , 'Ilford HP5'                          , 'Black & White',  0,  1,  0, 'AWB'  ,  0,  0,  1, 6, None),
    ('Ilford'              , 'Ilford FP4'                          , 'Black & White',  0,  1,  1, 'AWB'  ,  0,  0,  0, 6, None),
    ('Ilford'              , 'Ilford Delta 100'                    , 'Black & White',  0,  1,  1, 'AWB'  ,  0,  0,  0, 6, None),
    ('Ilford'              , 'Ilford Delta 3200'                   , 'Black & White',  0,  3, -2, 'AWB'  ,  0,  0,  2, 6, None),
    ('Ilford'              , 'Ilford Pan F 50'                     , 'Black & White',  0,  2,  2, 'AWB'  ,  0,  0,  0, 6, None),
]

# Recipe Lab's internal names, tidied for a photo app
RENAME = {"FACTORY (ST)": "Sony Standard"}

# Sony Creative Styles approximated as engine parameters
STYLE_BASE = {
    "Standard": {},
    "Vivid": {"saturation": 1.18, "contrast": 0.1},
    "Neutral": {"saturation": 0.88, "contrast": -0.08},
    "Portrait": {"saturation": 0.95, "contrast": -0.05, "temperature": 3, "hsl": {"orange": {"sat": 0.92}}},
    "Clear": {"saturation": 1.05, "contrast": 0.08, "highlights": 0.15},
    "Deep": {"saturation": 1.15, "contrast": 0.15, "exposure": -0.15},
    "Light": {"saturation": 0.9, "contrast": -0.15, "exposure": 0.2},
    "Landscape": {"saturation": 1.15, "hsl": {"green": {"sat": 1.1}, "blue": {"sat": 1.1}}},
    "Black & White": {"mono": True},
    "Sepia": {"mono": True, "split_shadows": [32, 0.55], "split_highlights": [42, 0.5]},
}

# Picture Effects approximated as engine parameters
EFFECT_BASE = {
    "Soft High-key": {"exposure": 0.5, "contrast": -0.4, "fade": 0.05, "saturation": 0.85,
                      "split_highlights": [210, 0.2]},
    "Retro Photo": {"saturation": 0.6, "contrast": -0.1, "fade": 0.07, "vignette": 0.35,
                    "split_shadows": [40, 0.35], "split_highlights": [48, 0.35]},
    "High Contrast Mono": {"mono": True, "contrast": 0.75, "fade": -0.05, "grain": 0.2},
    "Toy Camera": {"contrast": 0.3, "saturation": 1.2, "vignette": 0.7},
    "Pop Color": {"saturation": 1.5, "contrast": 0.15},
}

ADDITIVE = {"exposure", "temperature", "tint", "contrast", "highlights", "shadows"}

# Film character: what makes each stock look like itself beyond in-camera settings.
# Additive keys add, "saturation" multiplies, "hsl" merges, everything else replaces.
CHARACTER = {
    # Fuji simulations
    "Provia": {"hsl": {"blue": {"sat": 1.05}}},
    "Velvia": {"hsl": {"green": {"sat": 1.15}, "blue": {"sat": 1.1}, "red": {"hue": -4, "sat": 0.9}, "orange": {"sat": 0.9}}, "shadows": -0.1},
    "Astia": {"highlights": -0.2, "hsl": {"orange": {"sat": 0.9}}},
    "Classic Chrome": {"fade": 0.02, "hsl": {"blue": {"sat": 0.7, "hue": -5}, "red": {"sat": 0.85}, "green": {"sat": 0.8}},
                       "split_shadows": [200, 0.15], "split_highlights": [45, 0.1]},
    "Classic Negative": {"fade": 0.03, "hsl": {"red": {"hue": -6, "sat": 0.9}, "green": {"hue": 12}, "blue": {"hue": -8},
                                               "yellow": {"sat": 0.8}},
                         "split_shadows": [190, 0.35], "split_highlights": [40, 0.25]},
    "Nostalgic Neg": {"shadows": 0.1, "split_highlights": [40, 0.4], "hsl": {"red": {"sat": 1.05}}},
    "Reala Ace": {"hsl": {"orange": {"sat": 0.95}}},
    "Pro Neg Std": {"highlights": -0.2, "hsl": {"orange": {"sat": 0.9}}},
    "Pro Neg Hi": {"highlights": -0.1, "hsl": {"orange": {"sat": 0.92}}},
    "Eterna": {"fade": 0.04, "highlights": -0.4, "split_shadows": [190, 0.2]},
    "Eterna Bleach Bypass": {"saturation": 0.8, "fade": -0.02},
    "Acros": {"grain": 0.25},
    "Acros +Ye (yellow filter)": {"mono_mix": [0.40, 0.55, 0.05], "grain": 0.25},
    "Acros +R (red filter)": {"mono_mix": [0.70, 0.30, 0.0], "grain": 0.25},
    "Acros +G (green filter)": {"mono_mix": [0.20, 0.75, 0.05], "grain": 0.25},
    # Fuji film
    "Fuji Pro 400H": {"saturation": 0.85, "fade": 0.04, "hsl": {"green": {"hue": 10}}, "split_highlights": [190, 0.15], "grain": 0.2},
    "Fuji Fortia 50": {"hsl": {"red": {"sat": 1.15}}, "grain": 0.05},
    "Fuji Superia 400": {"hsl": {"green": {"hue": 8}}, "split_shadows": [140, 0.2], "grain": 0.25},
    "Fuji C200": {"fade": 0.03, "split_shadows": [150, 0.25], "grain": 0.2},
    "Fuji Natura 1600": {"fade": 0.03, "grain": 0.35},
    # Kodak
    "Kodak Portra 160": {"fade": 0.03, "highlights": -0.2, "hsl": {"orange": {"sat": 0.9, "hue": 2}}, "grain": 0.12},
    "Kodak Portra 400": {"fade": 0.03, "split_highlights": [40, 0.2], "hsl": {"orange": {"lum": 0.2}}, "grain": 0.18},
    "Kodak Portra 800": {"fade": 0.04, "split_shadows": [200, 0.15], "grain": 0.3},
    "Kodak Gold 200": {"split_highlights": [45, 0.35], "hsl": {"yellow": {"sat": 1.1}, "blue": {"sat": 0.9}}, "grain": 0.2},
    "Kodak Ultra Max 400": {"hsl": {"red": {"sat": 1.1}, "yellow": {"sat": 1.05}}, "grain": 0.25},
    "Kodak Color Plus 200": {"fade": 0.03, "split_highlights": [42, 0.2], "grain": 0.25},
    "Kodak Ektar 100": {"hsl": {"red": {"sat": 1.15}, "blue": {"sat": 1.15, "hue": -6}}, "grain": 0.05},
    "Kodak Ektachrome E100": {"hsl": {"blue": {"sat": 1.15}}, "split_shadows": [220, 0.2], "grain": 0.05},
    "Kodachrome 64": {"fade": -0.02, "hsl": {"red": {"sat": 1.15, "hue": -3}, "yellow": {"sat": 1.1}, "blue": {"sat": 1.05, "hue": 5}},
                      "grain": 0.1},
    "Kodak Vision3 500T (daylight)": {"highlights": -0.3, "split_shadows": [195, 0.3], "split_highlights": [35, 0.2], "grain": 0.2},
    "Kodak Vision 200T (Asteroid City)": {"fade": 0.05, "hsl": {"green": {"hue": -10, "sat": 0.9}, "blue": {"hue": -15}}, "grain": 0.15},
    "Kodak Tri-X 400": {"mono_mix": [0.35, 0.55, 0.10], "grain": 0.45},
    "Kodak T-Max": {"grain": 0.15},
    "Kodak Tri-X 1600 (pushed)": {"fade": -0.03, "grain": 0.7},
    # Cine
    "Cinestill 50D (Blue Velvet)": {"fade": 0.03, "split_highlights": [25, 0.1], "grain": 0.15},
    "Cinestill 800T": {"split_shadows": [200, 0.35], "split_highlights": [20, 0.25], "grain": 0.3},
    "Classic Cinema": {"split_shadows": [195, 0.35], "split_highlights": [35, 0.3], "hsl": {"blue": {"hue": -10}, "orange": {"sat": 1.05}}},
    "Rec709 Video (flat-ish)": {"fade": 0.02},
    # Ricoh GR
    "GR Positive Film": {"hsl": {"red": {"sat": 1.1}, "blue": {"sat": 1.1}}},
    "GR Negative Film": {"fade": 0.04, "split_shadows": [190, 0.25]},
    "GR Bleach Bypass": {"saturation": 0.8},
    "GR Retro": {"saturation": 0.9},
    "GR Cross Process": {"split_shadows": [230, 0.35], "split_highlights": [70, 0.45], "hsl": {"green": {"hue": 10}}},
    "GR Hi-Contrast B&W": {"fade": -0.06, "grain": 0.35, "vignette": 0.2},
    "GR Hard Monotone": {"grain": 0.25},
    "GR Soft Monotone": {"fade": 0.05},
    # Leica
    "Leica Classic": {"saturation": 0.95, "split_highlights": [40, 0.1]},
    "Leica Eternal": {"fade": 0.04, "split_shadows": [190, 0.2]},
    "Leica Monochrom": {"grain": 0.1},
    # Hasselblad, Canon, Nikon
    "Hasselblad HNCS Natural": {"hsl": {"orange": {"sat": 0.95}}},
    "Canon Standard": {"hsl": {"red": {"sat": 1.05}}},
    "Canon Portrait": {"hsl": {"orange": {"sat": 0.92}}},
    "Nikon Flat": {"highlights": -0.3},
    # Panasonic, Olympus
    "Pana L.ClassicNeo": {"fade": 0.05, "split_shadows": [190, 0.2], "split_highlights": [45, 0.25], "grain": 0.2},
    "Olympus Pop Art": {"saturation": 1.15},
    "Olympus Pale & Light": {"fade": 0.05, "split_highlights": [200, 0.15]},
    # Other stocks
    "Agfa Vista 200": {"hsl": {"red": {"sat": 1.15}}, "split_shadows": [200, 0.15], "grain": 0.25},
    "Agfa Ultra 100": {"hsl": {"red": {"sat": 1.1}}, "grain": 0.1},
    "Polaroid / Instax": {"saturation": 1.4, "fade": 0.07, "vignette": 0.3,
                          "split_shadows": [180, 0.3], "split_highlights": [50, 0.25]},
    # Ilford
    "Ilford HP5": {"mono_mix": [0.33, 0.56, 0.11], "grain": 0.45},
    "Ilford FP4": {"grain": 0.2},
    "Ilford Delta 100": {"grain": 0.1},
    "Ilford Delta 3200": {"fade": 0.03, "grain": 0.8},
    "Ilford Pan F 50": {"grain": 0.05},
}


def merge(base: dict, extra: dict) -> dict:
    """Layer ``extra`` on top of ``base`` (see ADDITIVE for how keys combine)."""
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if k in ADDITIVE:
            out[k] = out.get(k, 0.0) + v
        elif k == "saturation":
            out[k] = out.get(k, 1.0) * v
        elif k == "hsl":
            hsl = out.setdefault("hsl", {})
            for name, adj in v.items():
                cur = hsl.setdefault(name, {})
                for a, val in adj.items():
                    if a == "sat":
                        cur["sat"] = cur.get("sat", 1.0) * val
                    else:
                        cur[a] = cur.get(a, 0.0) + val
        else:
            out[k] = copy.deepcopy(v)
    return out


def recipe_params(style, sat, con, sharp, wb, ab, gm, ev, dro, effect) -> dict:
    """Translate one in-camera recipe into engine parameters."""
    p = merge({}, STYLE_BASE[style])
    if effect:
        p = merge(p, EFFECT_BASE[effect])
    p = merge(p, {"saturation": 1.0 + 0.08 * sat, "contrast": 0.09 * con})
    if wb != "AWB":
        kelvin = int(wb.rstrip("K"))
        p = merge(p, {"temperature": 1e6 / 5500.0 - 1e6 / kelvin})
    p = merge(p, {"temperature": 6.0 * ab, "tint": float(gm), "exposure": ev / 3.0})
    shadows = -0.15 if dro == 0 else 0.1 if dro == 6 else 0.08 * dro - 0.05
    p = merge(p, {"shadows": shadows})
    # sharpness is a spatial setting a LUT cannot carry; it is kept for reference only
    return p


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _build() -> list[dict]:
    looks = []
    for brand, name, style, sat, con, sharp, wb, ab, gm, ev, dro, effect in RECIPES:
        params = recipe_params(style, sat, con, sharp, wb, ab, gm, ev, dro, effect)
        params = merge(params, CHARACTER.get(name, {}))
        if params.get("mono"):
            params.pop("hsl", None)
        looks.append({"id": slug(name), "name": RENAME.get(name, name), "brand": brand,
                      "params": params, "builtin": True})
    return looks


BUILTIN = _build()
BRANDS = list(dict.fromkeys(l["brand"] for l in BUILTIN))
