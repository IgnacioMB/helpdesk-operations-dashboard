"""Colour-palette validator: OKLab Delta E, Vienot dichromat simulation, WCAG contrast.

The categorical slots in app/theme.py were chosen by running this, not by eye.

Usage:
    python tools/validate_palette.py "#00A58E,#0172CB,#E8552A" "#FFFFFF" "Kiwi series"
    python tools/validate_palette.py            # runs the checks behind the README claims
"""
import numpy as np, itertools, sys
def hex2rgb(h):
    h=h.lstrip('#'); return np.array([int(h[i:i+2],16)/255 for i in (0,2,4)])
def srgb2lin(c): return np.where(c<=0.04045, c/12.92, ((c+0.055)/1.055)**2.4)
def lin2srgb(c): return np.where(c<=0.0031308, c*12.92, 1.055*np.clip(c,0,None)**(1/2.4)-0.055)
M1=np.array([[0.4122214708,0.5363325363,0.0514459929],[0.2119034982,0.6806995451,0.1073969566],[0.0883024619,0.2817188376,0.6299787005]])
M2=np.array([[0.2104542553,0.7936177850,-0.0040720468],[1.9779984951,-2.4285922050,0.4505937099],[0.0259040371,0.7827717662,-0.8086757660]])
def oklab(rgb):
    l=M1@srgb2lin(rgb); return M2@np.cbrt(l)
def dE(a,b): return float(np.linalg.norm(oklab(hex2rgb(a))-oklab(hex2rgb(b)))*100)
# Viénot/Brettel LMS dichromat simulation
RGB2LMS=np.array([[17.8824,43.5161,4.11935],[3.45565,27.1554,3.86714],[0.0299566,0.184309,1.46709]])
LMS2RGB=np.linalg.inv(RGB2LMS)
SIM={'protan':np.array([[0,2.02344,-2.52581],[0,1,0],[0,0,1]]),
     'deutan':np.array([[1,0,0],[0.494207,0,1.24827],[0,0,1]]),
     'tritan':np.array([[1,0,0],[0,1,0],[-0.395913,0.801109,0]])}
def cvd(h,kind):
    lin=srgb2lin(hex2rgb(h)); lms=RGB2LMS@lin
    out=LMS2RGB@(SIM[kind]@lms)
    return '#%02x%02x%02x'%tuple(int(round(x*255)) for x in np.clip(lin2srgb(np.clip(out,0,None)),0,1))
def lum(h):
    r,g,b=srgb2lin(hex2rgb(h)); return 0.2126*r+0.7152*g+0.0722*b
def contrast(a,b):
    l1,l2=sorted([lum(a),lum(b)],reverse=True); return (l1+0.05)/(l2+0.05)
def report(pal,surface,label):
    print(f"\n### {label}  surface={surface}")
    ok=True
    for c in pal:
        cr=contrast(c,surface)
        flag='PASS' if cr>=3 else 'WARN'
        if cr<3: ok=False
        print(f"  contrast {c} vs surface = {cr:.2f}:1  [{flag}]")
    for a,b in itertools.combinations(pal,2):
        n=dE(a,b); worst=min(dE(cvd(a,k),cvd(b,k)) for k in SIM)
        fn='PASS' if n>=15 else 'FAIL'
        fc='PASS' if worst>=8 else ('WARN' if worst>=6 else 'FAIL')
        if n<15 or worst<6: ok=False
        print(f"  {a} vs {b}: normal dE={n:5.1f} [{fn}]  worst-CVD dE={worst:5.1f} [{fc}]")
    print("  ==>", "ALL GATES PASS" if ok else "ISSUES ABOVE")
    return ok
if __name__=="__main__":
    if len(sys.argv) > 1:
        pal=sys.argv[1].split(','); surf=sys.argv[2] if len(sys.argv)>2 else "#FFFFFF"
        ok=report(pal,surf,sys.argv[3] if len(sys.argv)>3 else "palette")
        sys.exit(0 if ok else 1)
    # Default: reproduce the claims made in README.md and app/theme.py
    ok = report(["#00A58E","#0172CB","#E8552A"], "#FFFFFF",
                "Kiwi categorical slots (README: worst normal dE 19.7, worst CVD 10.7, min contrast 3.10)")
    report(["#2a78d6","#eb6834","#1baf7a"], "#fcfcfb",
           "control: the data-viz skill's documented slots 1-3 (published: normal 24.0)")
    sys.exit(0 if ok else 1)
