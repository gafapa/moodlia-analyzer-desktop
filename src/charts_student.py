"""Student-level chart functions for the analysis dashboard."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
import matplotlib.ticker as mticker
import numpy as np
try:
    import seaborn as sns
    _HAS_SEABORN = True
except ImportError:
    _HAS_SEABORN = False

from .charts_base import COLORS, RISK_PALETTE, _apply_dark_style, _kde_line, _draw_semicircle_gauge, _style_seaborn_colorbar


# ============================================================
# Student detail charts
# ============================================================

def chart_student_radar(metrics: Dict, figsize=(4.5, 4.5),
                         course_avg_metrics: Optional[Dict] = None) -> Figure:
    """Plot a radar chart and optionally compare it with course averages."""
    def metric_or_zero(key: str) -> float:
        value = metrics.get(key)
        return float(value) if value is not None else 0.0

    # Visual label and metric key pairs for available components.
    axes_def = [("Engagement", "engagement_score")]
    if (metrics.get("total_activities") or 0) > 0:
        axes_def.append(("Completitud", "completion_rate"))
    if (metrics.get("total_assignments") or 0) > 0:
        axes_def.extend([("Entregas", "submission_rate"), ("A Tiempo", "on_time_rate")])
    if (metrics.get("total_quizzes") or 0) > 0:
        axes_def.append(("Cuestion.", "quiz_avg_pct"))
    axes_def.append(("Académico", "academic_score"))

    categories  = [a[0] for a in axes_def]
    metric_keys = [a[1] for a in axes_def]
    values      = [metric_or_zero(k) for k in metric_keys]

    N      = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]
    values_plot = values + values[:1]

    fig = Figure(figsize=figsize, facecolor=COLORS["bg"])
    ax  = fig.add_subplot(111, polar=True)
    ax.set_facecolor(COLORS["bg_card"])

    ax.spines["polar"].set_color(COLORS["grid"])
    ax.spines["polar"].set_linewidth(0.8)
    ax.tick_params(colors=COLORS["text"])
    ax.set_rlabel_position(30)
    ax.yaxis.set_tick_params(labelsize=6)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(20))
    ax.grid(color=COLORS["grid"], linestyle="-", linewidth=0.4, alpha=0.5)

    # Draw the class average below the student series when available
    has_avg = course_avg_metrics is not None
    if has_avg:
        avg_values = [float(course_avg_metrics.get(k) or 0) for k in metric_keys]
        avg_values_plot = avg_values + avg_values[:1]
        ax.fill(angles, avg_values_plot, color=COLORS["neutral"], alpha=0.08)
        ax.plot(angles, avg_values_plot, color=COLORS["neutral"],
                linewidth=1.5, linestyle="--", alpha=0.65, label="Media clase")

    # Relleno exterior (glow)
    ax.fill(angles, values_plot, color=COLORS["primary"], alpha=0.12)
    # More opaque inner fill.
    ax.fill(angles, values_plot, color=COLORS["primary"], alpha=0.25)
    # Main student series
    ax.plot(angles, values_plot, color=COLORS["primary"],
            linewidth=2.5, solid_capstyle="round", label="Alumno")
    # Vertex markers.
    ax.scatter(angles[:-1], values, color=COLORS["accent"],
               s=55, zorder=5, edgecolors=COLORS["bg"], linewidths=1)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=8.5, color=COLORS["text"])

    if has_avg:
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1),
                  facecolor=COLORS["bg_card"], labelcolor=COLORS["text"], fontsize=7.5)

    fig.suptitle("Perfil del Alumno", color=COLORS["text"],
                 fontsize=11, fontweight="bold", y=0.98)
    fig.tight_layout()
    return fig


def chart_student_grade_timeline(metrics: Dict, figsize=(6, 3), pass_threshold_pct: float = 50.0) -> Figure:
    """Plot the grade timeline with a gradient fill below the curve."""
    items = metrics.get("grade_items", [])
    dated = [
        (i["gradedate"], i["grade_pct"], i["name"])
        for i in items
        if i.get("gradedate") and i.get("grade_pct") is not None
    ]
    dated.sort(key=lambda x: x[0])

    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    if not dated:
        ax.text(0.5, 0.5, "Sin calificaciones registradas",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Evolución de Calificaciones", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    dates  = [datetime.fromtimestamp(d[0]) for d in dated]
    grades = [d[1] for d in dated]
    names  = [d[2] for d in dated]

    # Subtle failing and passing regions.
    ax.axhspan(0, pass_threshold_pct, alpha=0.04, color=COLORS["alto"])
    ax.axhspan(pass_threshold_pct, 100, alpha=0.04, color=COLORS["bajo"])
    ax.axhline(pass_threshold_pct, color=COLORS["medio"], linestyle="--",
               linewidth=1.2, alpha=0.65, label=f"Aprobado ({pass_threshold_pct:.0f}%)")

    # Gradient fill below the line
    ax.fill_between(dates, grades, 0, alpha=0.15, color=COLORS["primary"], zorder=1)
    ax.fill_between(dates, grades, 0, alpha=0.07, color=COLORS["primary"], zorder=1)

    # Main line.
    ax.plot(dates, grades, color=COLORS["primary"], linewidth=2.5,
            marker="o", markersize=7, markerfacecolor=COLORS["accent"],
            markeredgecolor=COLORS["bg"], markeredgewidth=1.2, zorder=3)

    # Anotaciones
    for date, grade, name in zip(dates, grades, names):
        ax.annotate(
            f"{grade:.0f}%", (date, grade),
            textcoords="offset points", xytext=(0, 9),
            ha="center", fontsize=7.5, color=COLORS["text"], alpha=0.9,
        )

    # Tendencia
    if len(grades) >= 3:
        x_num = np.array(range(len(grades)))
        z = np.polyfit(x_num, grades, 1)
        p = np.poly1d(z)
        ax.plot(dates, p(x_num), color=COLORS["secondary"], linestyle=":",
                linewidth=1.8, alpha=0.75, label="Tendencia")

    ax.set_ylim(0, 112)
    ax.set_ylabel("Calificación (%)")
    ax.set_title("Evolución de Calificaciones", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    ax.legend(facecolor=COLORS["bg_card"], labelcolor=COLORS["text"], fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def chart_student_activity_bars(metrics: Dict, figsize=(5, 3.5)) -> Figure:
    """Render student metric bars with traffic-light colors."""
    def metric_or_zero(key: str) -> float:
        value = metrics.get(key)
        return float(value) if value is not None else 0.0

    labels = ["Engagement"]
    student_vals = [metric_or_zero("engagement_score")]
    if (metrics.get("total_activities") or 0) > 0:
        labels.append("Completitud")
        student_vals.append(metric_or_zero("completion_rate"))
    if (metrics.get("total_assignments") or 0) > 0:
        labels.extend(["Entregas", "A Tiempo"])
        student_vals.extend([
            metric_or_zero("submission_rate"),
            metric_or_zero("on_time_rate"),
        ])

    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    x = np.arange(len(labels))
    bar_colors = [
        COLORS["bajo"] if v >= 70 else (COLORS["medio"] if v >= 45 else COLORS["alto"])
        for v in student_vals
    ]

    bars = ax.bar(x, student_vals, color=bar_colors, edgecolor="none",
                  alpha=0.88, width=0.6, zorder=2)

    for bar, val in zip(bars, student_vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.2,
            f"{val:.0f}%",
            ha="center", va="bottom",
            color=COLORS["text"], fontsize=9.5, fontweight="bold",
        )

    ax.axhline(70, color=COLORS["neutral"], linestyle="--",
               linewidth=1, alpha=0.5, label="70%")
    ax.set_ylim(0, 118)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=COLORS["text"])
    ax.set_ylabel("Porcentaje (%)")
    ax.set_title("Indicadores de Actividad", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    ax.legend(facecolor=COLORS["bg_card"], labelcolor=COLORS["text"], fontsize=8)
    fig.tight_layout()
    return fig


def chart_student_quiz_history(attempts: List[Dict], quizzes: List[Dict],
                                figsize=(5, 3), pass_threshold_pct: float = 50.0) -> Figure:
    """Render quiz result bars."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    if not attempts:
        ax.text(0.5, 0.5, "Sin intentos de cuestionario",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Cuestionarios", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    quiz_map = {q["id"]: q for q in quizzes}
    points   = []
    for att in attempts:
        state = att.get("state", "")
        if state not in ("finished", "gradedright", "gradedwrong", "gradedpartial"):
            continue
        grade = att.get("grade")
        if grade is None:
            continue
        quiz  = quiz_map.get(att.get("quizid"), {})
        max_g = float(quiz.get("grade", 10) or 10)
        pct   = (float(grade) / max_g) * 100 if max_g > 0 else 0
        name  = quiz.get("name", f"Quiz {att.get('quizid')}")[:18]
        ts    = att.get("timefinish", 0)
        points.append((ts, pct, name))

    points.sort(key=lambda x: x[0])

    if not points:
        ax.text(0.5, 0.5, "Sin intentos completados",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Cuestionarios", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    x_pos = range(len(points))
    pctes  = [p[1] for p in points]
    names  = [p[2] for p in points]
    colors = [COLORS["bajo"] if p >= pass_threshold_pct else COLORS["alto"] for p in pctes]

    bars = ax.bar(x_pos, pctes, color=colors, edgecolor="none",
                  alpha=0.88, zorder=2)
    for bar, val in zip(bars, pctes):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.2,
                f"{val:.0f}%", ha="center", va="bottom",
                color=COLORS["text"], fontsize=8.5)

    ax.axhline(pass_threshold_pct, color=COLORS["medio"], linestyle="--",
               linewidth=1.2, alpha=0.7, label=f"Aprobado ({pass_threshold_pct:.0f}%)")
    ax.set_ylim(0, 118)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(names, rotation=30, ha="right",
                       fontsize=7, color=COLORS["text"])
    ax.set_ylabel("Puntuación (%)")
    ax.set_title("Resultados de Cuestionarios", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    ax.legend(facecolor=COLORS["bg_card"], labelcolor=COLORS["text"], fontsize=8)
    fig.tight_layout()
    return fig


def chart_student_submissions_timeline(
    submissions: List[Dict], assignments: List[Dict], figsize=(9, 5)
) -> Figure:
    """Plot every assignment submission against its due date and status."""
    if not assignments:
        fig, ax = plt.subplots(figsize=figsize)
        _apply_dark_style(fig, ax)
        ax.text(0.5, 0.5, "Sin tareas en el curso",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Historial de Entregas", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    n     = len(assignments)
    fig_h = max(figsize[1], n * 0.45 + 1.5)
    fig, ax = plt.subplots(figsize=(figsize[0], fig_h))
    _apply_dark_style(fig, ax)

    sub_map = {s["assignid"]: s for s in submissions}
    now     = datetime.now()

    for i, assign in enumerate(assignments):
        aid    = assign.get("id")
        due    = assign.get("duedate", 0)
        sub    = sub_map.get(aid)
        status = sub.get("status", "") if sub else ""
        y      = i

        if due:
            due_dt = datetime.fromtimestamp(due)
            ax.scatter(due_dt, y, color=COLORS["neutral"], marker="|",
                       s=220, linewidths=2, zorder=3)

        if status == "submitted":
            sub_ts = sub.get("timemodified", 0) or sub.get("timecreated", 0)
            if sub_ts:
                sub_dt = datetime.fromtimestamp(sub_ts)
                color  = COLORS["bajo"] if (not due or sub_ts <= due) else COLORS["alto"]
                ax.scatter(sub_dt, y, color=color, marker="o",
                           s=90, zorder=4, edgecolors=COLORS["bg"], linewidths=0.8)
                if due:
                    due_dt2 = datetime.fromtimestamp(due)
                    ax.hlines(y, min(sub_dt, due_dt2), max(sub_dt, due_dt2),
                              color=color, linewidth=1.5, alpha=0.4)
            else:
                if due:
                    ax.scatter(datetime.fromtimestamp(due), y,
                               color=COLORS["bajo"], marker="o",
                               s=90, zorder=4)

        elif status in ("draft", "new"):
            sub_ts = sub.get("timemodified", 0) or sub.get("timecreated", 0)
            ref = datetime.fromtimestamp(sub_ts) if sub_ts else (
                datetime.fromtimestamp(due) if due else now
            )
            ax.scatter(ref, y, color=COLORS["medio"], marker="D",
                       s=65, zorder=4)
        else:
            if due and datetime.fromtimestamp(due) < now:
                ax.scatter(now, y, color=COLORS["alto"], marker="x",
                           s=90, zorder=4, linewidths=2.2)

    ax.set_yticks(range(n))
    ax.set_yticklabels(
        [a.get("name", f"Tarea {i+1}")[:28] for i, a in enumerate(assignments)],
        fontsize=7, color=COLORS["text"],
    )

    legend_items = [
        mpatches.Patch(color=COLORS["bajo"],    label="Entregado a tiempo"),
        mpatches.Patch(color=COLORS["alto"],    label="Tarde / No entregado"),
        mpatches.Patch(color=COLORS["medio"],   label="Borrador (sin enviar)"),
        mpatches.Patch(color=COLORS["neutral"], label="Fecha límite"),
    ]
    ax.legend(handles=legend_items, facecolor=COLORS["bg_card"],
              labelcolor=COLORS["text"], fontsize=7, loc="lower right")
    ax.set_title("Historial de Entregas", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def chart_prediction_gauge(prediction: Dict, metrics: Dict,
                            figsize=(5, 3.2), pass_threshold_pct: float = 50.0) -> Figure:
    """Plot semicircular gauges for the predicted grade and risk."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
    fig.patch.set_facecolor(COLORS["bg"])
    for ax in (ax1, ax2):
        ax.set_facecolor(COLORS["bg"])

    pred_pct  = float(prediction.get("predicted_grade_pct", 0))
    max_g     = float(metrics.get("course_total_max") or 10.0)
    pred_grade= float(prediction.get("predicted_grade", 0))
    risk_pct  = float(prediction.get("risk_probability", 0)) * 100

    grade_color = COLORS["bajo"] if pred_pct >= pass_threshold_pct else COLORS["alto"]
    risk_color  = (
        COLORS["alto"]  if risk_pct > 60 else
        COLORS["medio"] if risk_pct > 30 else
        COLORS["bajo"]
    )

    _draw_semicircle_gauge(ax1, pred_pct,  grade_color,
                           "Nota Estimada",
                           sublabel=f"{pred_grade:.1f} / {max_g:.0f}")
    _draw_semicircle_gauge(ax2, risk_pct, risk_color,
                           "Riesgo de Suspenso")

    method = prediction.get("method", "heuristic")
    fig.text(0.5, 0.01,
             f"Método: {'Machine Learning (GBT)' if method == 'ml' else 'Heurístico'}",
             ha="center", fontsize=7, color=COLORS["fg_dim"])
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    return fig


def chart_student_activity_heatmap_week(
    timestamps: List[int], figsize=(5, 3.5)
) -> Figure:
    """Plot an activity heat map by weekday and hour, using seaborn when available."""
    DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    matrix = np.zeros((7, 24), dtype=int)

    for ts in timestamps:
        try:
            dt = datetime.fromtimestamp(ts)
            matrix[dt.weekday(), dt.hour] += 1
        except (OSError, ValueError, OverflowError):
            pass

    fig, ax = plt.subplots(figsize=figsize)

    if not timestamps or matrix.max() == 0:
        _apply_dark_style(fig, ax)
        ax.text(0.5, 0.5, "Sin registros de actividad disponibles",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Patrón Horario de Actividad", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    hour_labels = [str(h) if h % 3 == 0 else "" for h in range(24)]

    if _HAS_SEABORN:
        fig.patch.set_facecolor(COLORS["bg"])
        ax.set_facecolor(COLORS["bg_card"])
        sns.heatmap(
            matrix,
            xticklabels=hour_labels,
            yticklabels=DAYS,
            cmap="YlOrRd",
            vmin=0, vmax=max(1, matrix.max()),
            linewidths=0.3,
            linecolor=COLORS["bg"],
            ax=ax,
            cbar_kws={"shrink": 0.75, "aspect": 28},
        )
        ax.set_facecolor(COLORS["bg_card"])
        ax.tick_params(colors=COLORS["text"], labelsize=7.5, length=0)
        ax.set_xticklabels(ax.get_xticklabels(), color=COLORS["text"])
        ax.set_yticklabels(ax.get_yticklabels(), color=COLORS["text"], rotation=0)
        _style_seaborn_colorbar(ax)
    else:
        _apply_dark_style(fig, ax)
        im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto",
                       vmin=0, vmax=max(1, matrix.max()))
        ax.set_yticks(range(7))
        ax.set_yticklabels(DAYS, fontsize=8, color=COLORS["text"])
        ax.set_xticks(range(0, 24, 3))
        ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 3)],
                           fontsize=7, color=COLORS["text"])
        cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        plt.setp(cbar.ax.yaxis.get_ticklabels(), color=COLORS["text"], fontsize=7)

    # Annotate peak activity
    max_idx = np.unravel_index(matrix.argmax(), matrix.shape)
    DAYS_FULL = ["Lunes", "Martes", "Miércoles", "Jueves",
                 "Viernes", "Sábado", "Domingo"]
    ax.set_xlabel(
        f"Pico: {DAYS_FULL[max_idx[0]]} a las {max_idx[1]:02d}h",
        fontsize=8, color=COLORS["accent"],
    )
    ax.set_title("Patrón Horario de Actividad", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    fig.patch.set_facecolor(COLORS["bg"])
    fig.tight_layout()
    return fig


def chart_student_weekly_activity(
    timestamps: List[int],
    session_count: Optional[int] = None,
    avg_session_min: Optional[float] = None,
    weeks_active: Optional[int] = None,
    figsize=(5, 3.5),
) -> Figure:
    """Plot weekly activity with a session-statistics summary."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    if not timestamps:
        ax.text(0.5, 0.5, "Sin datos de actividad",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Actividad Semanal", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    week_counts: Dict[str, int] = {}
    week_dates:  Dict[str, datetime] = {}
    for ts in timestamps:
        try:
            dt     = datetime.fromtimestamp(ts)
            monday = dt - timedelta(days=dt.weekday())
            key    = monday.strftime("%Y-%W")
            week_counts[key] = week_counts.get(key, 0) + 1
            if key not in week_dates:
                week_dates[key] = monday
        except (OSError, ValueError, OverflowError):
            pass

    if not week_counts:
        ax.text(0.5, 0.5, "Sin datos de actividad",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Actividad Semanal", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    sorted_keys = sorted(week_dates.keys())
    labels  = [week_dates[k].strftime("%d/%m") for k in sorted_keys]
    counts  = [week_counts[k] for k in sorted_keys]
    max_c   = max(counts) if counts else 1

    bar_colors = [
        COLORS["bajo"]  if c >= max_c * 0.65 else
        COLORS["medio"] if c >= max_c * 0.30 else
        COLORS["alto"]
        for c in counts
    ]

    x = range(len(labels))
    ax.bar(x, counts, color=bar_colors, edgecolor="none", alpha=0.88, zorder=2)

    # KDE semanal suave si hay suficientes semanas
    if len(counts) >= 4:
        x_k, y_k = _kde_line(
            [i for i, c in enumerate(counts) for _ in range(c)],
            x_min=-0.5, x_max=len(counts) - 0.5, bandwidth=1.2
        )
        if len(x_k):
            scale = len(counts) * max_c * 0.35
            ax.plot(x_k, y_k * scale, color=COLORS["text"],
                    linewidth=1.8, alpha=0.5, zorder=4)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right",
                       fontsize=7, color=COLORS["text"])
    ax.set_ylabel("Eventos registrados", fontsize=8)
    ax.set_title("Actividad Semanal", fontsize=11, fontweight="bold",
                 color=COLORS["text"])

    # Session statistics box.
    info_parts: List[str] = []
    if session_count is not None:
        info_parts.append(f"Sesiones: {session_count}")
    if avg_session_min is not None:
        info_parts.append(f"Duración media: {avg_session_min:.0f} min")
    if weeks_active is not None:
        info_parts.append(f"Semanas activas: {weeks_active}")
    if info_parts:
        ax.text(0.02, 0.97, "\n".join(info_parts),
                transform=ax.transAxes, ha="left", va="top",
                fontsize=7.5, color=COLORS["accent"],
                bbox=dict(facecolor=COLORS["bg_card"], alpha=0.88,
                          edgecolor=COLORS["border"], boxstyle="round,pad=0.4"))
    else:
        ax.text(0.5, 0.02,
                "Logs no disponibles — datos desde entregas, quizzes y foros",
                transform=ax.transAxes, ha="center", fontsize=7,
                color=COLORS["fg_dim"], style="italic")

    fig.tight_layout()
    return fig


def chart_submission_advance_bars(
    submissions: List[Dict], assignments: List[Dict], figsize=(5, 4)
) -> Figure:
    """Plot assignment lead time with on-time and late status colors."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    if not assignments:
        ax.text(0.5, 0.5, "Sin tareas en el curso",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Antelación en Entregas", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    sub_map = {s["assignid"]: s for s in submissions}
    now     = datetime.now()

    names:    List[str]   = []
    advances: List[float] = []
    bar_cols: List[str]   = []

    for assign in assignments:
        aid  = assign.get("id")
        due  = assign.get("duedate", 0)
        if not due:
            continue
        name   = assign.get("name", "Tarea")[:24]
        sub    = sub_map.get(aid)
        status = sub.get("status", "submitted") if sub else ""

        if sub and status not in ("new", "draft", "reopened"):
            ts = sub.get("timemodified", 0) or sub.get("timecreated", 0)
            if ts:
                advance = (due - ts) / 86400.0
                names.append(name)
                advances.append(advance)
                bar_cols.append(COLORS["bajo"] if advance >= 0 else COLORS["alto"])
        elif datetime.fromtimestamp(due) < now:
            names.append(f"✗ {name}")
            advances.append(-7.0)
            bar_cols.append(COLORS["alto"])

    if not names:
        ax.text(0.5, 0.5, "Sin tareas con fecha límite registradas",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=9)
        ax.set_title("Antelación en Entregas", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    y = list(range(len(names)))
    ax.barh(y, advances, color=bar_cols, edgecolor="none", alpha=0.88, zorder=2)
    ax.axvline(0, color=COLORS["neutral"], linewidth=1.8,
               linestyle="--", alpha=0.7)

    for yi, val, name in zip(y, advances, names):
        if "✗" in name:
            ax.text(0.3, yi, "No entregada", va="center", ha="left",
                    color=COLORS["alto"], fontsize=7)
        else:
            lbl = f"+{val:.1f}d" if val >= 0 else f"{val:.1f}d"
            ha  = "left" if val >= 0 else "right"
            x_off = val + 0.2 if val >= 0 else val - 0.2
            ax.text(x_off, yi, lbl, va="center", ha=ha,
                    color=COLORS["text"], fontsize=7)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=7, color=COLORS["text"])
    ax.set_xlabel("Días respecto al plazo  (+ = entregó antes)",
                  fontsize=8, color=COLORS["text"])
    ax.set_title("Antelación en Entregas", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    fig.tight_layout()
    return fig


def chart_student_percentile(student: Dict, all_students: List[Dict],
                              figsize=(7, 4.5)) -> Figure:
    """Plot the student's percentile for each key metric against the class."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    m = student.get("metrics", {})

    # Label, metric key, and whether higher values are better.
    has_completion = any((s.get("metrics", {}).get("total_activities") or 0) > 0 for s in all_students)
    has_assignments = any((s.get("metrics", {}).get("total_assignments") or 0) > 0 for s in all_students)
    has_quizzes = any((s.get("metrics", {}).get("total_quizzes") or 0) > 0 for s in all_students)
    has_forums = any((s.get("metrics", {}).get("total_forums") or 0) > 0 for s in all_students)

    metrics_def = [
        ("Nota final",        "final_grade_pct",     True),
        ("Engagement",        "engagement_score",    True),
    ]
    if has_assignments:
        metrics_def.append(("Tasa de entregas", "submission_rate", True))
    if has_completion:
        metrics_def.append(("Completitud", "completion_rate", True))
    if has_quizzes:
        metrics_def.append(("Quiz avg", "quiz_avg_pct", True))
    if has_forums:
        metrics_def.append(("Posts en foros", "forum_posts_count", True))
    metrics_def.append(("Días sin acceso", "days_since_access", False))  # menor = mejor

    labels, percentiles, colors_list = [], [], []

    for label, key, higher_better in metrics_def:
        val = m.get(key)
        if val is None:
            continue
        all_vals = [s.get("metrics", {}).get(key)
                    for s in all_students
                    if s.get("metrics", {}).get(key) is not None]
        if len(all_vals) < 2:
            continue
        below = sum(1 for v in all_vals if v < val)
        pct   = below / len(all_vals) * 100
        if not higher_better:
            pct = 100 - pct
        labels.append(label)
        percentiles.append(pct)
        colors_list.append(
            COLORS["bajo"]   if pct >= 65 else
            COLORS["medio"]  if pct >= 35 else
            COLORS["alto"]
        )

    if not labels:
        ax.text(0.5, 0.5, "Sin datos suficientes para calcular percentiles",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=11)
        ax.set_title("Posición del Alumno en el Grupo",
                     fontsize=11, fontweight="bold", color=COLORS["text"])
        fig.tight_layout()
        return fig

    y    = np.arange(len(labels))
    bars = ax.barh(y, percentiles, color=colors_list, height=0.55,
                   alpha=0.85, edgecolor="none", zorder=2)

    # Numeric label on each bar.
    for bar, pct in zip(bars, percentiles):
        x_lbl = min(pct + 2, 92)
        ax.text(x_lbl, bar.get_y() + bar.get_height() / 2,
                f"{pct:.0f}° pct.", va="center",
                color=COLORS["text"], fontsize=8.5)

    # Median line and neutral region.
    ax.axvline(50, color=COLORS["fg_dim"], linewidth=1.2,
               linestyle="--", alpha=0.6, label="Mediana (50°)")
    ax.fill_betweenx([-0.5, len(labels) - 0.5], 35, 65,
                     color=COLORS["neutral"], alpha=0.06)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=COLORS["text"], fontsize=9)
    ax.set_xlim(0, 104)
    ax.set_xlabel("Percentil en el grupo (100 = mejor de la clase)",
                  color=COLORS["text"])
    ax.set_title(
        f"Posición de {student.get('fullname', 'Alumno')[:30]} en el Grupo",
        fontsize=11, fontweight="bold", color=COLORS["text"])
    ax.legend(facecolor=COLORS["bg_card"], edgecolor=COLORS["border"],
              labelcolor=COLORS["text"], fontsize=8)
    fig.tight_layout()
    return fig
