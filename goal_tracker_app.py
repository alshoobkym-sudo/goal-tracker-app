with open("goal_tracker_app.py", "w", encoding="utf-8") as f:
    f.write('''import datetime as dt
from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st

DATA = Path("data")
DATA.mkdir(exist_ok=True)
GF, LF = DATA / "goals.csv", DATA / "log.csv"
GCOLS = ["goal", "unit", "target", "base", "start", "end", "ms", "res"]
LCOLS = ["date", "goal", "units", "period", "hours", "note"]
st.set_page_config("Goal Tracker", "🎯", layout="wide")

GOALS_DEFAULT = [
    {"goal": "Master German (A1-B2)", "unit": "Pages", "target": 800, "base": 0, "start": str(dt.date.today()), "end": str(dt.date.today() + dt.timedelta(days=180)), "ms": 200, "res": "Grammatik aktiv"},
    {"goal": "Bulking & Fitness", "unit": "kg", "target": 75, "base": 64, "start": str(dt.date.today()), "end": str(dt.date.today() + dt.timedelta(days=90)), "ms": 70, "res": "Protein diet"}
]

def read(path, default, datecols):
    df = pd.read_csv(path) if path.exists() else default
    for c in datecols:
        df[c] = pd.to_datetime(df[c]).dt.date
    return df

def load_goals():
    return read(GF, pd.DataFrame(GOALS_DEFAULT), ["start", "end"])[GCOLS]

def load_log():
    df = read(LF, pd.DataFrame(columns=LCOLS), ["date"])
    df["units"] = df["units"].astype(float)
    return df

def metrics(goals, log, today):
    wk0, mo0, yr0 = today - dt.timedelta(days=today.weekday()), today.replace(day=1), today.replace(month=1, day=1)
    out = []
    for r in goals.itertuples():
        l = log[log.goal == r.goal]
        s = lambda since: float(l.loc[l.date >= since, "units"].sum())
        done = r.base + float(l.units.sum())
        total, span = r.target - r.base, max(1, (r.end - r.start).days)
        el = min(1, max(0, (today - r.start).days / span))
        comp = min(1, done / r.target) if r.target else 0
        idx = 1 if el == 0 else (done - r.base) / (total * el) if total else 0
        recent = s(today - dt.timedelta(days=28)) / 4
        speed = recent if recent > 0 else (done - r.base) / max(1, (today - r.start).days / 7)
        rem = max(0, r.target - done)
        req = 0 if rem == 0 else rem / max(1, (r.end - today).days / 7)
        fin = today if rem == 0 else (today + dt.timedelta(weeks=min(rem / speed, 5000)) if speed > 0 else None)
        young = (today - r.start).days < 14
        gap = max(0, r.ms - done)
        if comp >= 1:
            status, dec = "Done", "Goal complete: set a new target."
        elif young:
            status, dec = "Warming up", "Too early to judge: keep logging for two weeks."
        else:
            status = "Ahead" if idx >= 1.05 else "On track" if idx >= 0.85 else "Behind" if idx >= 0.6 else "Critical"
            if idx >= 0.85:
                dec = "STAY THE COURSE: your pace matches the plan."
            elif speed > 0 and req / speed <= 1.5:
                dec = f"ADJUST: raise effort from {speed:.1f} to {req:.1f} {r.unit}/week to finish on time."
            else:
                dec = f"PIVOT: you need {req:.1f} {r.unit}/week but do {speed:.1f}. Change method, cut scope or move the deadline."
        wgap = gap / speed if speed > 0 else None
        need = ("Milestone reached: set the next one." if gap == 0 else
                f"Next milestone needs {gap:,.0f} more {r.unit}" + (f" (~{wgap:.1f} weeks at current pace)." if wgap else ".") +
                (f" Plan: {r.res}" if isinstance(r.res, str) and r.res else ""))
        out.append(dict(goal=r.goal, unit=r.unit, target=r.target, done=done, comp=comp, exp=(r.base + total * el) / r.target if r.target else 0,
                        idx=idx, status=status, dec=dec, need=need, speed=speed, req=req, fin=fin,
                        days=(r.end - fin).days if fin else None,
                        wk=s(wk0), wk_t=total / max(1, span / 7), mo=s(mo0), mo_t=total / max(1, span / 30.4375),
                        yr=s(yr0), yr_t=total * min(1, 365 / span)))
    return out

goals, log = load_goals(), load_log()
tab_dash, tab_log, tab_goals, tab_exp = st.tabs(["📊 Dashboard", "📝 Log progress", "🎯 Goals", "📤 Export"])

with tab_dash:
    M = metrics(goals, log, dt.date.today())
    if M:
        st.bar_chart(pd.DataFrame({"Completed": [m["comp"] for m in M], "Expected by today": [m["exp"] for m in M]},
                                  index=[m["goal"] for m in M]))
    for m in M:
        st.subheader(m["goal"])
        st.progress(m["comp"], text=f"{m['comp']:.0%} complete · expected {m['exp']:.0%} today · {m['status']}")
        a, b, c, d = st.columns(4)
        a.metric("Done", f"{m['done']:,.0f} / {m['target']:,.0f} {m['unit']}")
        b.metric("Pace (last 4 weeks)", f"{m['speed']:.1f}/wk", f"need {m['req']:.1f}/wk", delta_color="off")
        c.metric("Forecast finish", str(m["fin"]) if m["fin"] else "n/a",
                 f"{m['days']:+d} days vs deadline" if m["days"] is not None else None)
        d.metric("Week / month / YTD", f"{m['wk']:.0f} / {m['mo']:.0f} / {m['yr']:.0f}")
        kind = st.success if m["dec"].startswith(("STAY", "Goal")) else st.error if m["dec"].startswith("PIVOT") else st.warning if m["dec"].startswith("ADJUST") else st.info
        kind(f"**{m['dec']}**\\n\\n{m['need']}")
    with st.expander("Weekly · monthly · yearly detail"):
        st.dataframe(pd.DataFrame([{"Goal": m["goal"], "Week": m["wk"], "Week target": m["wk_t"], "Month": m["mo"],
                                    "Month target": m["mo_t"], "YTD": m["yr"], "Year target": m["yr_t"]} for m in M]).round(1))

def save_log(df):
    df.to_csv(LF, index=False)
    st.rerun()

with tab_log:
    st.caption("Date = the END of the period you are reporting. Don't log the same stretch twice at different granularities.")
    for tab, period in zip(st.tabs(["Weekly", "Monthly", "Yearly"]), ["Week", "Month", "Year"]):
        with tab, st.form(period, clear_on_submit=True):
            g = st.selectbox("Goal", goals.goal)
            d = st.date_input(f"{period} ending on", dt.date.today())
            u = st.number_input(f"Units completed this {period.lower()}", min_value=0.0, step=1.0)
            h = st.number_input("Hours spent", min_value=0.0, step=0.5)
            n = st.text_input("Note (blockers, what worked)")
            if st.form_submit_button("Save entry"):
                st.toast("Saved ✅")
                save_log(pd.concat([log, pd.DataFrame([[d, g, u, period, h, n]], columns=LCOLS)], ignore_index=True))
    st.dataframe(log.tail(10), hide_index=True)
    if st.button("Undo last entry") and len(log):
        save_log(log.iloc[:-1])

with tab_goals:
    st.caption("Edit targets, baselines, dates and milestones. Add or delete rows as needed.")
    ed = st.data_editor(goals.assign(start=pd.to_datetime(goals.start), end=pd.to_datetime(goals.end)), num_rows="dynamic",
                        column_config={"start": st.column_config.DateColumn(), "end": st.column_config.DateColumn()})
    if st.button("Save goals"):
        ed = ed.dropna(subset=["goal", "target", "start", "end"]).fillna({"base": 0, "ms": 0, "unit": "", "res": ""})
        ed.assign(start=ed.start.dt.date, end=ed.end.dt.date).to_csv(GF, index=False)
        st.rerun()

with tab_exp:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        goals.to_excel(writer, sheet_name="Goals", index=False)
        log.to_excel(writer, sheet_name="Log", index=False)
    
    st.download_button("⬇ Excel tracker with your data (.xlsx)", buf.getvalue(), "goal_tracker.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("⬇ Log only (.csv)", log.to_csv(index=False), "goal_log.csv", "text/csv")
    st.markdown("**Google Sheets:** upload the .xlsx to Drive and open with Sheets.")
''')
