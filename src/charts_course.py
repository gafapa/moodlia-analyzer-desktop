"""Course-level chart functions for the analysis dashboard."""
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
# Course dashboard charts
# ============================================================

def chart_risk_donut(course_metrics: Dict, figsize=(4, 4)) -> Figure:
    """Render a donut chart showing the risk-level distribution."""
    high   = course_metrics.get("at_risk_high",   0)
    medium = course_metrics.get("at_risk_medium",  0)
    low    = course_metrics.get("at_risk_low",     0)
    total  = high + medium + low

    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    if total == 0:
        ax.text(0.5, 0.5, "Sin datos", transform=ax.transAxes,
                ha="center", va="center", color=COLORS["text"], fontsize=12)
        ax.set_title("Distribución de Riesgo", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    values  = [low, medium, high]
    labels  = [f"Bajo\n{low}", f"Medio\n{medium}", f"Alto\n{high}"]
    colors  = [COLORS["bajo"], COLORS["medio"], COLORS["alto"]]
    explode = (0, 0.04, 0.08)

    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct="%1.0f%%",
        colors=colors,
        explode=explode,
        startangle=90,
        pctdistance=0.78,
        wedgeprops={"linewidth": 2.5, "edgecolor": COLORS["bg"]},
        shadow=False,
    )
    for txt in texts:
        txt.set_color(COLORS["text"])
        txt.set_fontsize(8)
        txt.set_fontweight("bold")
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(8.5)
        at.set_fontweight("bold")

    # Agujero central
    circle = plt.Circle((0, 0), 0.54, color=COLORS["bg_card"])
    ax.add_patch(circle)
    ax.text(0,  0.12, str(total), ha="center", va="center",
            fontsize=26, fontweight="bold", color=COLORS["text"])
    ax.text(0, -0.12, "alumnos", ha="center", va="center",
            fontsize=8.5, color=COLORS["fg_dim"])

    ax.set_title("Distribución de Riesgo", fontsize=11, fontweight="bold",
                 color=COLORS["text"], pad=12)
    fig.tight_layout()
    return fig


def chart_engagement_histogram(all_students: List[Dict], figsize=(5, 3.5)) -> Figure:
    """Plot engagement distribution with a smooth KDE curve and risk colors."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    values = [s["metrics"].get("engagement_score", 0)
              for s in all_students if "metrics" in s]
    if not values:
        ax.text(0.5, 0.5, "Sin datos", transform=ax.transAxes,
                ha="center", va="center", color=COLORS["text"])
        ax.set_title("Distribución de Engagement", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    bins = np.linspace(0, 100, 11)
    n, bins_out, patches = ax.hist(
        values, bins=bins,
        edgecolor=COLORS["bg"], linewidth=0.6, alpha=0.85, zorder=2,
    )
    # Color by risk level
    for patch, left in zip(patches, bins_out[:-1]):
        if left < 30:
            patch.set_facecolor(COLORS["alto"])
        elif left < 60:
            patch.set_facecolor(COLORS["medio"])
        else:
            patch.set_facecolor(COLORS["bajo"])

    # KDE suave (numpy puro)
    if len(values) >= 3:
        x_k, y_k = _kde_line(values, x_min=0, x_max=100, bandwidth=9)
        if len(x_k):
            ax.plot(x_k, y_k, color=COLORS["text"], linewidth=2,
                    alpha=0.75, zorder=5, label="Densidad")
            ax.fill_between(x_k, y_k, alpha=0.08, color=COLORS["text"], zorder=4)

    # Mean reference line.
    mean_val = float(np.mean(values))
    ax.axvline(mean_val, color=COLORS["accent"], linestyle="--", linewidth=1.8,
               label=f"Media: {mean_val:.0f}", zorder=6)
    ax.legend(facecolor=COLORS["bg_card"], labelcolor=COLORS["text"],
              fontsize=8, framealpha=0.9)

    ax.set_xlabel("Índice de Engagement (0-100)")
    ax.set_ylabel("N.º Alumnos")
    ax.set_title("Distribución de Engagement", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    ax.set_xlim(0, 100)
    fig.tight_layout()
    return fig


def chart_grade_distribution(course_metrics: Dict, figsize=(5, 3.5),
                              pass_threshold_pct: float = 50.0) -> Figure:
    """Plot grade distribution bars with floating labels."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    dist   = course_metrics.get("grade_distribution", {})
    labels = list(dist.keys())
    values = list(dist.values())

    if not any(values):
        ax.text(0.5, 0.5, "Sin datos de calificaciones", transform=ax.transAxes,
                ha="center", va="center", color=COLORS["text"], fontsize=10)
        ax.set_title("Distribución de Calificaciones", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    # Dynamic colors based on the active passing threshold
    _range_bounds = [(0, 19), (20, 39), (40, 59), (60, 79), (80, 100)]
    bar_colors = []
    for lo, hi in _range_bounds:
        if hi < pass_threshold_pct:
            bar_colors.append(COLORS["alto"])   # rango totalmente suspenso
        elif lo >= pass_threshold_pct:
            bar_colors.append(COLORS["bajo"])   # rango totalmente aprobado
        else:
            bar_colors.append(COLORS["medio"])  # rango que cruza el umbral
    bars = ax.bar(labels, values, color=bar_colors,
                  edgecolor=COLORS["bg"], linewidth=0.6, alpha=0.88,
                  width=0.65, zorder=2)

    # Labels above the bars
    for bar, val in zip(bars, values):
        if val > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.15,
                str(int(val)),
                ha="center", va="bottom",
                color=COLORS["text"], fontsize=9.5, fontweight="bold",
            )

    ax.set_xlabel("Rango de Nota (%)")
    ax.set_ylabel("N.º Alumnos")
    ax.set_title("Distribución de Calificaciones", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    ax.set_ylim(0, max(values) * 1.28 + 1 if values else 5)
    fig.tight_layout()
    return fig


def chart_scatter_engagement_vs_grade(all_students: List[Dict],
                                       figsize=(5, 4)) -> Figure:
    """Plot engagement against grades with a trend confidence band."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    xs, ys, risk_levels = [], [], []
    for s in all_students:
        m    = s.get("metrics", {})
        eng  = m.get("engagement_score")
        grade= m.get("final_grade_pct")
        risk = s.get("risk_level", "bajo")
        if eng is None or grade is None:
            continue
        xs.append(eng)
        ys.append(grade)
        risk_levels.append(risk)

    if not xs:
        ax.text(0.5, 0.5, "Sin datos suficientes",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Engagement vs Calificación", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    # Color points by risk level
    for eng, grade, risk in zip(xs, ys, risk_levels):
        color = COLORS.get(risk, COLORS["neutral"])
        ax.scatter(eng, grade, c=color, alpha=0.82, s=70,
                   edgecolors=COLORS["bg"], linewidths=0.6, zorder=3)

    # Trend line with a shaded confidence band.
    if len(xs) >= 4:
        xs_arr = np.array(xs)
        ys_arr = np.array(ys)
        z = np.polyfit(xs_arr, ys_arr, 1)
        p = np.poly1d(z)
        x_line = np.linspace(min(xs_arr), max(xs_arr), 200)
        y_line = p(x_line)
    # Residual standard deviation for the band
        residuals = ys_arr - p(xs_arr)
        std = float(np.std(residuals))
        ax.plot(x_line, y_line, color=COLORS["primary"],
                linestyle="--", linewidth=2, alpha=0.9, label="Tendencia", zorder=4)
        ax.fill_between(x_line, y_line - std, y_line + std,
                        alpha=0.12, color=COLORS["primary"], zorder=2)

    legend_patches = [
        mpatches.Patch(color=COLORS["bajo"],  label="Riesgo Bajo"),
        mpatches.Patch(color=COLORS["medio"], label="Riesgo Medio"),
        mpatches.Patch(color=COLORS["alto"],  label="Riesgo Alto"),
    ]
    if len(xs) >= 4:
        legend_patches.append(
            mpatches.Patch(color=COLORS["primary"], alpha=0.6, label="Tendencia ±σ")
        )
    ax.legend(handles=legend_patches, facecolor=COLORS["bg_card"],
              labelcolor=COLORS["text"], fontsize=8, loc="upper left")

    ax.set_xlabel("Engagement (0-100)")
    ax.set_ylabel("Calificación (%)")
    ax.set_title("Engagement vs Calificación", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    ax.set_xlim(-5, 105)
    ax.set_ylim(-5, 105)
    fig.tight_layout()
    return fig


def chart_activity_heatmap(all_students: List[Dict], figsize=(6, 4)) -> Figure:
    """Plot a student-by-metric activity heat map, using seaborn when available."""
    has_completion = any((s.get("metrics", {}).get("total_activities") or 0) > 0 for s in all_students)
    has_assignments = any((s.get("metrics", {}).get("total_assignments") or 0) > 0 for s in all_students)
    has_quizzes = any((s.get("metrics", {}).get("total_quizzes") or 0) > 0 for s in all_students)

    metrics_keys = [("engagement_score", "Engagement")]
    if has_completion:
        metrics_keys.append(("completion_rate", "Completitud"))
    if has_assignments:
        metrics_keys.extend([
            ("submission_rate", "Entregas"),
            ("on_time_rate", "A tiempo"),
        ])
    if has_quizzes:
        metrics_keys.append(("quiz_avg_pct", "Cuestion."))
    metrics_keys.append(("academic_score", "Académico"))

    students_sorted = sorted(
        all_students, key=lambda s: s.get("risk_level", "bajo"), reverse=True
    )[:30]

    fig, ax = plt.subplots(figsize=figsize)

    if not students_sorted:
        _apply_dark_style(fig, ax)
        ax.text(0.5, 0.5, "Sin datos", transform=ax.transAxes,
                ha="center", va="center", color=COLORS["text"])
        return fig

    names      = [s.get("fullname", "?")[:20] for s in students_sorted]
    col_labels = [lbl for _, lbl in metrics_keys]
    data_arr   = np.array([
        [s.get("metrics", {}).get(k) or 0 for k, _ in metrics_keys]
        for s in students_sorted
    ], dtype=float)

    do_annot = len(students_sorted) <= 15

    if _HAS_SEABORN:
        fig.patch.set_facecolor(COLORS["bg"])
        ax.set_facecolor(COLORS["bg_card"])

        sns.heatmap(
            data_arr,
            xticklabels=col_labels,
            yticklabels=names,
            cmap="RdYlGn",
            vmin=0, vmax=100,
            annot=do_annot,
            fmt=".0f",
            annot_kws={"size": 6, "color": COLORS["text"], "weight": "bold"},
            linewidths=0.4,
            linecolor=COLORS["bg"],
            ax=ax,
            cbar_kws={"shrink": 0.75, "aspect": 28},
        )
        ax.set_facecolor(COLORS["bg_card"])
        ax.tick_params(colors=COLORS["text"], labelsize=7, length=0)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right",
                           color=COLORS["text"], fontsize=8)
        ax.set_yticklabels(ax.get_yticklabels(), color=COLORS["text"], fontsize=7)
        _style_seaborn_colorbar(ax)
    else:
        _apply_dark_style(fig, ax)
        im = ax.imshow(data_arr, cmap="RdYlGn", aspect="auto", vmin=0, vmax=100)
        ax.set_xticks(range(len(col_labels)))
        ax.set_xticklabels(col_labels, rotation=35, ha="right",
                           fontsize=8, color=COLORS["text"])
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=7, color=COLORS["text"])
        if do_annot:
            for i in range(len(students_sorted)):
                for j in range(len(metrics_keys)):
                    val = data_arr[i, j]
                    ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                            fontsize=6, color="black" if 30 < val < 70 else "white")
        cbar = fig.colorbar(im, ax=ax, fraction=0.03)
        cbar.ax.yaxis.set_tick_params(color=COLORS["text"], labelsize=7)
        plt.setp(cbar.ax.yaxis.get_ticklabels(), color=COLORS["text"])

    ax.set_title("Mapa de Calor: Métricas por Alumno",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    fig.patch.set_facecolor(COLORS["bg"])
    fig.tight_layout()
    return fig


def chart_top_risk_bar(all_students: List[Dict], top_n: int = 10,
                        figsize=(5, 4)) -> Figure:
    """Render horizontal bars for the students at highest risk."""
    high_risk   = [s for s in all_students if s.get("risk_level") == "alto"]
    medium_risk = [s for s in all_students if s.get("risk_level") == "medio"]
    target = (high_risk + medium_risk)[:top_n]

    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    if not target:
        ax.text(0.5, 0.5, "¡Sin alumnos en riesgo!", transform=ax.transAxes,
                ha="center", va="center", color=COLORS["bajo"],
                fontsize=13, fontweight="bold")
        ax.set_title("Alumnos en Mayor Riesgo", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    names      = [s.get("fullname", "?")[:26] for s in reversed(target)]
    scores     = [s["metrics"].get("engagement_score", 0) for s in reversed(target)]
    bar_colors = [COLORS[s.get("risk_level", "bajo")] for s in reversed(target)]

    bars = ax.barh(names, scores, color=bar_colors, edgecolor="none",
                   alpha=0.88, height=0.65, zorder=2)

    for bar, val in zip(bars, scores):
        ax.text(val + 0.8, bar.get_y() + bar.get_height() / 2,
                f"{val:.0f}", va="center", color=COLORS["text"],
                fontsize=8.5, fontweight="bold")

    ax.set_xlim(0, 112)
    ax.set_xlabel("Índice de Engagement")
    ax.set_title(f"Alumnos en Mayor Riesgo (Top {len(target)})",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    # Reference line.
    ax.axvline(30, color=COLORS["alto"], linestyle=":", linewidth=1, alpha=0.5)
    ax.axvline(60, color=COLORS["bajo"], linestyle=":", linewidth=1, alpha=0.5)
    fig.tight_layout()
    return fig


def chart_correlation_matrix(all_students: List[Dict], figsize=(5, 4)) -> Figure:
    """Plot a correlation matrix for student metrics, using seaborn when available."""
    has_completion = any((s.get("metrics", {}).get("total_activities") or 0) > 0 for s in all_students)
    has_assignments = any((s.get("metrics", {}).get("total_assignments") or 0) > 0 for s in all_students)
    has_quizzes = any((s.get("metrics", {}).get("total_quizzes") or 0) > 0 for s in all_students)
    has_forums = any((s.get("metrics", {}).get("total_forums") or 0) > 0 for s in all_students)

    keys = [("engagement_score", "Engagement")]
    if has_completion:
        keys.append(("completion_rate", "Completitud"))
    if has_assignments:
        keys.append(("submission_rate", "Entregas"))
    if has_quizzes:
        keys.append(("quiz_avg_pct", "Cuestion."))
    if has_forums:
        keys.append(("forum_posts_count", "Foros"))
    keys.append(("final_grade_pct", "Nota"))

    fig, ax = plt.subplots(figsize=figsize)

    data_cols, labels = [], []
    for key, label in keys:
        col = [s["metrics"].get(key) for s in all_students
               if s.get("metrics", {}).get(key) is not None]
        if len(col) >= 3:
            data_cols.append(col[:len(all_students)])
            labels.append(label)

    if len(data_cols) < 2:
        _apply_dark_style(fig, ax)
        ax.text(0.5, 0.5, "Insuficientes datos para\ncalcular correlaciones",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Correlación entre Métricas", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    min_len     = min(len(c) for c in data_cols)
    matrix_data = np.array([c[:min_len] for c in data_cols], dtype=float)

    # Drop constant columns to avoid division by zero in np.corrcoef
    stds        = matrix_data.std(axis=1)
    valid_mask  = stds > 1e-9
    if valid_mask.sum() < 2:
        _apply_dark_style(fig, ax)
        ax.text(0.5, 0.5, "Métricas sin variación suficiente",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Correlación entre Métricas", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig
    matrix_data = matrix_data[valid_mask]
    labels      = [lbl for lbl, ok in zip(labels, valid_mask) if ok]

    corr_matrix = np.corrcoef(matrix_data)
    # Replace any remaining NaN values with zero
    corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)

    if _HAS_SEABORN:
        fig.patch.set_facecolor(COLORS["bg"])
        ax.set_facecolor(COLORS["bg_card"])
        sns.heatmap(
            corr_matrix,
            xticklabels=labels,
            yticklabels=labels,
            cmap="RdYlGn",
            vmin=-1, vmax=1,
            annot=False,   # anotaciones manuales para control de color
            linewidths=0.4,
            linecolor=COLORS["bg"],
            ax=ax,
            cbar_kws={"shrink": 0.75, "aspect": 28},
        )
        ax.set_facecolor(COLORS["bg_card"])
        ax.tick_params(colors=COLORS["text"], labelsize=8, length=0)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right",
                           color=COLORS["text"], fontsize=8)
        ax.set_yticklabels(ax.get_yticklabels(), color=COLORS["text"],
                           fontsize=8, rotation=0)
        _style_seaborn_colorbar(ax)
    # Manual annotations with contrast-aware colors
        for i in range(len(labels)):
            for j in range(len(labels)):
                val = corr_matrix[i, j]
                tc  = "black" if -0.25 < val < 0.25 else "white"
                ax.text(j + 0.5, i + 0.5, f"{val:.2f}",
                        ha="center", va="center",
                        fontsize=7.5, color=tc, fontweight="bold")
    else:
        _apply_dark_style(fig, ax)
        im = ax.imshow(corr_matrix, cmap="RdYlGn", vmin=-1, vmax=1)
        ax.set_xticks(range(len(labels)))
        ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=35, ha="right",
                           fontsize=8, color=COLORS["text"])
        ax.set_yticklabels(labels, fontsize=8, color=COLORS["text"])
        for i in range(len(labels)):
            for j in range(len(labels)):
                val = corr_matrix[i, j]
                tc  = "black" if -0.3 < val < 0.3 else "white"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=7, color=tc)
        cbar = fig.colorbar(im, ax=ax, fraction=0.04)
        plt.setp(cbar.ax.yaxis.get_ticklabels(), color=COLORS["text"], fontsize=7)

    ax.set_title("Correlación entre Métricas", fontsize=11, fontweight="bold",
                 color=COLORS["text"])
    fig.patch.set_facecolor(COLORS["bg"])
    fig.tight_layout()
    return fig


# ============================================================
# Additional course analysis charts
# ============================================================

def chart_course_funnel(all_students: List[Dict], figsize=(7, 4)) -> Figure:
    """Plot enrollment, access, submission, completion, and risk as a course funnel."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    n = len(all_students)
    if n == 0:
        ax.text(0.5, 0.5, "Sin datos de alumnos", transform=ax.transAxes,
                ha="center", va="center", color=COLORS["text"], fontsize=10)
        ax.set_title("Progresión del Curso", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    has_assignments = any((s.get("metrics", {}).get("total_assignments") or 0) > 0 for s in all_students)
    has_completion = any((s.get("metrics", {}).get("total_activities") or 0) > 0 for s in all_students)

    stages = [
        ("Matriculados", n, COLORS["primary"]),
        ("Accedieron",
         sum(1 for s in all_students if s.get("lastaccess", 0) > 0),
         COLORS["accent"]),
    ]
    if has_assignments:
        stages.append((
            "Entregaron algo",
            sum(1 for s in all_students if s.get("metrics", {}).get("submitted_assignments", 0) > 0),
            COLORS["bajo"],
        ))
    if has_completion:
        stages.append((
            "Completitud >50 %",
            sum(1 for s in all_students if (s.get("metrics", {}).get("completion_rate") or 0) > 50),
            COLORS["accent2"],
        ))
    stages.append((
        "Sin riesgo alto",
        sum(1 for s in all_students if s.get("risk_level") != "alto"),
        COLORS["bajo"],
    ))

    labels = [s[0] for s in stages]
    values = [s[1] for s in stages]
    colors = [s[2] for s in stages]

    y_pos = range(len(labels))
    bars  = ax.barh(y_pos, values, color=colors, edgecolor="none",
                    alpha=0.88, height=0.55, zorder=2)

    for bar, val in zip(bars, values):
        pct = val / n * 100 if n > 0 else 0
        ax.text(
            val + n * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{val}  ({pct:.0f}%)",
            va="center", color=COLORS["text"], fontsize=9, fontweight="bold",
        )

    # Drop-off between stages
    for i in range(1, len(values)):
        drop = values[i - 1] - values[i]
        if drop > 0:
            ax.text(
                values[i] / 2,
                i - 0.5,
                f"−{drop}",
                ha="center", va="center",
                color=COLORS["fg_dim"], fontsize=7.5, style="italic",
            )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, color=COLORS["text"], fontsize=9)
    ax.set_xlabel("N.º Alumnos")
    ax.set_xlim(0, n * 1.38)
    ax.set_title("Funnel de Progresión del Curso",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    ax.invert_yaxis()
    fig.tight_layout()
    return fig


def chart_submissions_heatmap(all_students: List[Dict], assignments: List[Dict],
                               figsize=(10, 6)) -> Figure:
    """Plot student-by-assignment submission status ordered by engagement and due date."""
    from matplotlib.colors import LinearSegmentedColormap

    if not all_students or not assignments:
        fig, ax = plt.subplots(figsize=figsize)
        _apply_dark_style(fig, ax)
        ax.text(0.5, 0.5, "Sin datos de tareas", transform=ax.transAxes,
                ha="center", va="center", color=COLORS["text"], fontsize=10)
        ax.set_title("Mapa de Entregas", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    sorted_assigns = sorted(
        assignments,
        key=lambda a: (a.get("duedate") or 9_999_999_999),
    )
    sorted_students = sorted(
        all_students,
        key=lambda s: s.get("metrics", {}).get("engagement_score", 0),
        reverse=True,
    )

    assign_labels  = [a.get("name", "?")[:16] for a in sorted_assigns]
    student_labels = [s.get("fullname", "?")[:22] for s in sorted_students]

    now    = datetime.now().timestamp()
    matrix = np.full((len(sorted_students), len(sorted_assigns)), -1.0)

    for i, student in enumerate(sorted_students):
        sub_map = {sub["assignid"]: sub for sub in student.get("submissions", [])}
        for j, assign in enumerate(sorted_assigns):
            aid    = assign.get("id")
            due    = assign.get("duedate", 0)
            sub    = sub_map.get(aid)
            status = sub.get("status", "") if sub else ""

            if status == "submitted":
                ts = sub.get("timemodified", 0) or sub.get("timecreated", 0)
                matrix[i, j] = 2.0 if (not due or ts <= due) else 1.0
            elif status in ("draft", "new"):
                matrix[i, j] = 1.0
            elif due and due < now:
                matrix[i, j] = 0.0
            # else -1: pendiente, no vencido

    cmap_sub  = LinearSegmentedColormap.from_list(
        "sub3", [COLORS["alto"], COLORS["medio"], COLORS["bajo"]], N=256)
    mask_pend = matrix < 0
    disp      = np.where(mask_pend, np.nan, matrix)

    fig, ax = plt.subplots(figsize=figsize)

    if _HAS_SEABORN:
        fig.patch.set_facecolor(COLORS["bg"])
        ax.set_facecolor(COLORS["bg_card"])
        sns.heatmap(
            disp,
            xticklabels=assign_labels,
            yticklabels=student_labels,
            cmap=cmap_sub,
            vmin=0, vmax=2,
            mask=mask_pend,
            linewidths=0.25,
            linecolor=COLORS["bg"],
            ax=ax,
            cbar=False,
        )
        for i in range(len(sorted_students)):
            for j in range(len(sorted_assigns)):
                if mask_pend[i, j]:
                    ax.add_patch(plt.Rectangle(
                        (j, i), 1, 1,
                        fill=True, facecolor=COLORS["grid"],
                        edgecolor=COLORS["bg"], linewidth=0.25,
                    ))
        ax.set_facecolor(COLORS["bg_card"])
        ax.tick_params(colors=COLORS["text"], labelsize=7, length=0)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right",
                           color=COLORS["text"], fontsize=7)
        ax.set_yticklabels(ax.get_yticklabels(), color=COLORS["text"], fontsize=7)
    else:
        _apply_dark_style(fig, ax)
        ax.imshow(disp, cmap=cmap_sub, aspect="auto", vmin=0, vmax=2)
        ax.set_xticks(range(len(assign_labels)))
        ax.set_xticklabels(assign_labels, rotation=35, ha="right",
                           fontsize=7, color=COLORS["text"])
        ax.set_yticks(range(len(student_labels)))
        ax.set_yticklabels(student_labels, fontsize=7, color=COLORS["text"])

    legend_items = [
        mpatches.Patch(color=COLORS["bajo"],   label="A tiempo"),
        mpatches.Patch(color=COLORS["medio"],  label="Tarde / borrador"),
        mpatches.Patch(color=COLORS["alto"],   label="No entregado"),
        mpatches.Patch(color=COLORS["grid"],   label="Pendiente"),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=7,
              facecolor=COLORS["bg_card"], labelcolor=COLORS["text"],
              framealpha=0.9, bbox_to_anchor=(1.0, -0.18))

    ax.set_title("Mapa de Entregas  (Alumnos × Tareas)",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    fig.patch.set_facecolor(COLORS["bg"])
    fig.tight_layout()
    return fig


def chart_top_bottom_comparison(all_students: List[Dict],
                                 figsize=(8, 4.5)) -> Figure:
    """Compare five key metrics for the top and bottom academic quartiles."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    if len(all_students) < 4:
        ax.text(0.5, 0.5, "Se necesitan al menos 4 alumnos",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Top 25% vs Bottom 25%", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    sorted_s = sorted(
        all_students,
        key=lambda s: (s.get("metrics", {}).get("academic_score") or
                       s.get("metrics", {}).get("engagement_score", 0)),
        reverse=True,
    )
    group_n = max(1, len(sorted_s) // 4)
    top    = sorted_s[:group_n]
    bottom = sorted_s[-group_n:]

    has_completion = any((s.get("metrics", {}).get("total_activities") or 0) > 0 for s in all_students)
    has_assignments = any((s.get("metrics", {}).get("total_assignments") or 0) > 0 for s in all_students)
    has_quizzes = any((s.get("metrics", {}).get("total_quizzes") or 0) > 0 for s in all_students)

    metric_specs = [("engagement_score", "Engagement")]
    if has_completion:
        metric_specs.append(("completion_rate", "Completitud"))
    if has_assignments:
        metric_specs.extend([
            ("submission_rate", "Entregas"),
            ("on_time_rate", "A Tiempo"),
        ])
    if has_quizzes:
        metric_specs.append(("quiz_avg_pct", "Cuestion."))

    def _avg(group, key):
        vals = [s.get("metrics", {}).get(key) or 0 for s in group]
        return float(np.mean(vals)) if vals else 0.0

    top_vals    = [_avg(top,    k) for k, _ in metric_specs]
    bottom_vals = [_avg(bottom, k) for k, _ in metric_specs]
    labels      = [lbl for _, lbl in metric_specs]

    x = np.arange(len(labels))
    w = 0.38

    bars1 = ax.bar(x - w / 2, top_vals,    w, color=COLORS["bajo"],
                   edgecolor="none", alpha=0.88,
                   label=f"Top {group_n}  (mejor nota)")
    bars2 = ax.bar(x + w / 2, bottom_vals, w, color=COLORS["alto"],
                   edgecolor="none", alpha=0.88,
                   label=f"Bottom {group_n}  (peor nota)")

    for bar, val in zip(list(bars1) + list(bars2), top_vals + bottom_vals):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.5,
                f"{val:.0f}",
                ha="center", va="bottom",
                color=COLORS["text"], fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=COLORS["text"])
    ax.set_ylim(0, 120)
    ax.set_ylabel("Valor promedio (%)")
    ax.set_title("Top 25 % vs Bottom 25 % — ¿Qué hacen diferente?",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    ax.legend(facecolor=COLORS["bg_card"], labelcolor=COLORS["text"],
              fontsize=8, framealpha=0.9)
    fig.tight_layout()
    return fig


def chart_quiz_difficulty(all_students: List[Dict], quizzes: List[Dict],
                           figsize=(8, 4.5), pass_threshold_pct: float = 50.0) -> Figure:
    """Plot average score and pass rate by quiz, from hardest to easiest."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    if not quizzes:
        ax.text(0.5, 0.5, "Sin cuestionarios en el curso",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Dificultad de Cuestionarios", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    quiz_map = {q["id"]: q for q in quizzes}
    stats: Dict[int, Any] = {}

    for student in all_students:
        for att in student.get("quiz_attempts", []):
            qid   = att.get("quizid")
            state = att.get("state", "")
            if state not in ("finished", "gradedright", "gradedwrong", "gradedpartial"):
                continue
            grade = att.get("grade")
            quiz  = quiz_map.get(qid, {})
            max_g = float(quiz.get("grade", 10) or 10)
            if grade is None or max_g <= 0:
                continue
            pct = float(grade) / max_g * 100
            if qid not in stats:
                stats[qid] = {"name": quiz.get("name", f"Q{qid}")[:20],
                               "scores": [], "pass": 0, "total": 0}
            stats[qid]["scores"].append(pct)
            stats[qid]["total"] += 1
            if pct >= pass_threshold_pct:
                stats[qid]["pass"] += 1

    if not stats:
        ax.text(0.5, 0.5, "Sin intentos completados",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Dificultad de Cuestionarios", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    sorted_stats = sorted(stats.values(),
                          key=lambda x: float(np.mean(x["scores"])))

    names      = [s["name"] for s in sorted_stats]
    avgs       = [float(np.mean(s["scores"])) for s in sorted_stats]
    pass_rates = [s["pass"] / s["total"] * 100 if s["total"] else 0
                  for s in sorted_stats]
    attempts_n = [s["total"] for s in sorted_stats]

    x = np.arange(len(names))
    w = 0.38

    bar_colors = [COLORS["bajo"] if a >= pass_threshold_pct else COLORS["alto"] for a in avgs]
    bars1 = ax.bar(x - w / 2, avgs,       w, color=bar_colors,
                   edgecolor="none", alpha=0.88, label="Nota media (%)")
    bars2 = ax.bar(x + w / 2, pass_rates, w, color=COLORS["primary"],
                   edgecolor="none", alpha=0.75, label="Tasa de aprobados (%)")

    for xi, att_n in zip(x, attempts_n):
        ax.text(xi, 2, f"n={att_n}", ha="center", va="bottom",
                fontsize=7, color=COLORS["fg_dim"])

    ax.axhline(pass_threshold_pct, color=COLORS["medio"], linestyle="--",
               linewidth=1.2, alpha=0.7, label="Umbral aprobado")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=25, ha="right",
                       fontsize=8, color=COLORS["text"])
    ax.set_ylim(0, 118)
    ax.set_ylabel("Porcentaje (%)")
    ax.set_title("Dificultad por Cuestionario  (más difícil → más fácil)",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    ax.legend(facecolor=COLORS["bg_card"], labelcolor=COLORS["text"],
              fontsize=8, framealpha=0.9)
    fig.tight_layout()
    return fig


def chart_forum_activity(all_students: List[Dict], forums: List[Dict],
                          figsize=(7, 4)) -> Figure:
    """Plot inactive, low, and active participation per forum with post totals."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    if not forums:
        ax.text(0.5, 0.5, "Sin foros en el curso",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Participación en Foros", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    forum_stats: Dict[int, Dict] = {}
    for forum in forums:
        fid = forum.get("id")
        if fid is None:
            continue
        forum_stats[fid] = {
            "name":        forum.get("name", f"Foro {fid}")[:28],
            "none":        0,
            "low":         0,
            "active":      0,
            "total_posts": 0,
        }

    total_students = len(all_students)
    for student in all_students:
        pf: Dict[int, int] = {}
        for post in student.get("forum_posts", []):
            fid = post.get("forumid")
            if fid is not None:
                pf[fid] = pf.get(fid, 0) + 1
        for fid in forum_stats:
            cnt = pf.get(fid, 0)
            forum_stats[fid]["total_posts"] += cnt
            if cnt == 0:
                forum_stats[fid]["none"]   += 1
            elif cnt <= 2:
                forum_stats[fid]["low"]    += 1
            else:
                forum_stats[fid]["active"] += 1

    active = sorted(
        [v for v in forum_stats.values() if v["total_posts"] > 0],
        key=lambda x: x["total_posts"], reverse=True,
    )[:10]

    if not active:
        ax.text(0.5, 0.5, "Sin participación en foros registrada",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Participación en Foros", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    names    = [f["name"]        for f in active]
    none_v   = [f["none"]        for f in active]
    low_v    = [f["low"]         for f in active]
    active_v = [f["active"]      for f in active]
    totals   = [f["total_posts"] for f in active]

    x = np.arange(len(names))
    w = 0.6
    bottom_low    = none_v
    bottom_active = [a + b for a, b in zip(none_v, low_v)]

    ax.bar(x, none_v,   w, color=COLORS["grid"],   edgecolor="none",
           alpha=0.9,  label="Sin participar")
    ax.bar(x, low_v,    w, bottom=bottom_low,
           color=COLORS["medio"],  edgecolor="none", alpha=0.88,
           label="1-2 posts")
    ax.bar(x, active_v, w, bottom=bottom_active,
           color=COLORS["bajo"],   edgecolor="none", alpha=0.88,
           label="3+ posts (activo)")

    for xi, tot in zip(x, totals):
        ax.text(xi, total_students + 0.4,
                f"{tot} posts",
                ha="center", va="bottom",
                color=COLORS["accent"], fontsize=7.5, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=25, ha="right",
                       fontsize=8, color=COLORS["text"])
    ax.set_ylabel("N.º Alumnos")
    ax.set_ylim(0, total_students * 1.22 + 1)
    ax.set_title("Participación en Foros",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    ax.legend(facecolor=COLORS["bg_card"], labelcolor=COLORS["text"],
              fontsize=8, framealpha=0.9)
    fig.tight_layout()
    return fig


# ============================================================
# Cross-course comparison charts
# ============================================================

def chart_all_courses_enrollment(courses: List[Dict], figsize=(9, 5)) -> Figure:
    """Plot enrollment for up to 25 courses, ordered from highest to lowest."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    # Filter and sort courses with enrollment data
    valid = [c for c in courses if c.get("enrolledusercount") not in (None, "?", "")]
    if not valid:
        ax.text(0.5, 0.5, "Sin datos de matriculación disponibles",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Alumnos Matriculados por Curso",
                     fontsize=11, fontweight="bold", color=COLORS["text"])
        return fig

    valid.sort(key=lambda c: int(c.get("enrolledusercount", 0)), reverse=True)
    valid = valid[:25]  # Máx 25 cursos

    names  = [c.get("shortname") or c.get("fullname", "?")[:22] for c in valid]
    counts = [int(c.get("enrolledusercount", 0)) for c in valid]
    max_c  = max(counts) if counts else 1

    # Color by course size
    bar_colors = [
        COLORS["bajo"]    if n >= max_c * 0.6 else
        COLORS["primary"] if n >= max_c * 0.25 else
        COLORS["neutral"]
        for n in counts
    ]

    y = np.arange(len(names))
    bars = ax.barh(y, counts, color=bar_colors, edgecolor="none",
                   alpha=0.88, height=0.65, zorder=2)

    for bar, val in zip(bars, counts):
        ax.text(val + max_c * 0.008,
                bar.get_y() + bar.get_height() / 2,
                str(val),
                va="center", color=COLORS["text"], fontsize=8.5, fontweight="bold")

    # Media vertical
    mean_c = float(np.mean(counts))
    ax.axvline(mean_c, color=COLORS["accent"], linestyle="--",
               linewidth=1.5, alpha=0.7, label=f"Media: {mean_c:.0f}")

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8, color=COLORS["text"])
    ax.set_xlabel("N.º de alumnos matriculados")
    ax.set_xlim(0, max_c * 1.20)
    ax.set_title("Alumnos Matriculados por Curso",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    ax.legend(facecolor=COLORS["bg_card"], labelcolor=COLORS["text"],
              fontsize=8, framealpha=0.9)
    ax.invert_yaxis()
    fig.tight_layout()
    return fig


# ============================================================
# Additional charts: box plot, actual vs predicted, and bubbles
# ============================================================

def chart_grade_boxplot(all_students: List[Dict], figsize=(10, 5), pass_threshold_pct: float = 50.0) -> Figure:
    """Plot per-activity grade distributions, quartiles, medians, and outliers."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    # Aggregate grade items from all students by activity name
    grade_by_act: Dict[str, List[float]] = {}
    for s in all_students:
        for item in s.get("metrics", {}).get("grade_items", []):
            name = (item.get("name") or "?")[:24]
            pct  = item.get("grade_pct")
            if pct is not None:
                grade_by_act.setdefault(name, []).append(float(pct))

    # Keep groups with at least three values, sort by median, and show the top 14
    valid = {k: v for k, v in grade_by_act.items() if len(v) >= 3}
    if not valid:
        ax.text(0.5, 0.5, "Sin calificaciones registradas en el libro de notas",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=11)
        ax.set_title("Box Plot de Calificaciones por Actividad",
                     fontsize=11, fontweight="bold", color=COLORS["text"])
        fig.tight_layout()
        return fig

    sorted_acts = sorted(valid.items(), key=lambda x: np.median(x[1]))[-14:]
    names = [a[0] for a in sorted_acts]
    data  = [a[1] for a in sorted_acts]

    bp = ax.boxplot(
        data, patch_artist=True, vert=True,
        medianprops=dict(color=COLORS["accent2"], linewidth=2.5),
        whiskerprops=dict(color=COLORS["fg_dim"], linewidth=1.2),
        capprops=dict(color=COLORS["fg_dim"], linewidth=1.2),
        flierprops=dict(marker="o", color=COLORS["alto"],
                        alpha=0.7, markersize=4, linestyle="none"),
    )

    for i, patch in enumerate(bp["boxes"]):
        med = np.median(data[i])
        strong_threshold = min(100.0, pass_threshold_pct + 20.0)
        if med >= strong_threshold:
            face = COLORS["bajo"] + "44"
            edge = COLORS["bajo"]
        elif med >= pass_threshold_pct:
            face = COLORS["medio"] + "44"
            edge = COLORS["medio"]
        else:
            face = COLORS["alto"] + "44"
            edge = COLORS["alto"]
        patch.set_facecolor(face)
        patch.set_edgecolor(edge)

    ax.set_xticks(range(1, len(names) + 1))
    ax.set_xticklabels(names, rotation=32, ha="right",
                       color=COLORS["text"], fontsize=8)
    ax.axhline(pass_threshold_pct, color=COLORS["alto"],   linewidth=1.2, linestyle="--",
               alpha=0.6, label=f"Aprobado ({pass_threshold_pct:.0f}%)")
    ax.axhline(70, color=COLORS["neutral"], linewidth=0.8, linestyle=":",
               alpha=0.5, label="Notable (70%)")
    ax.set_ylabel("Calificación (%)", color=COLORS["text"])
    ax.set_title("Box Plot de Calificaciones por Actividad",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    ax.set_ylim(-5, 112)
    ax.legend(facecolor=COLORS["bg_card"], edgecolor=COLORS["border"],
              labelcolor=COLORS["text"], fontsize=8)
    fig.tight_layout()
    return fig


def chart_predicted_vs_actual(all_students: List[Dict], figsize=(8, 4.5), pass_threshold_pct: float = 50.0) -> Figure:
    """Compare overlapping distributions of current and predicted grades."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    actual    = [s.get("metrics", {}).get("final_grade_pct")
                 for s in all_students
                 if s.get("metrics", {}).get("final_grade_pct") is not None]
    predicted = [s.get("prediction", {}).get("predicted_grade_pct")
                 for s in all_students
                 if s.get("prediction", {}).get("predicted_grade_pct") is not None]

    if not actual and not predicted:
        ax.text(0.5, 0.5, "Sin datos de calificaciones o predicciones",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=11)
        ax.set_title("Notas Reales vs Predichas", fontsize=11,
                     fontweight="bold", color=COLORS["text"])
        fig.tight_layout()
        return fig

    bins = np.linspace(0, 100, 12)

    if actual:
        ax.hist(actual, bins=bins, color=COLORS["primary"], alpha=0.55,
                label=f"Nota real  (n={len(actual)}, media={np.mean(actual):.1f}%)",
                edgecolor=COLORS["bg"], linewidth=0.5, zorder=2)
        ax.axvline(np.mean(actual), color=COLORS["primary"],
                   linewidth=1.5, linestyle="--", alpha=0.8)

    if predicted:
        ax.hist(predicted, bins=bins, color=COLORS["accent2"], alpha=0.55,
                label=f"Nota predicha (n={len(predicted)}, media={np.mean(predicted):.1f}%)",
                edgecolor=COLORS["bg"], linewidth=0.5, zorder=3)
        ax.axvline(np.mean(predicted), color=COLORS["accent2"],
                   linewidth=1.5, linestyle="--", alpha=0.8)

    # Smooth KDE over each histogram.
    if actual and len(actual) > 3:
        xk, yk = _kde_line(actual, 0, 100, bandwidth=10)
        scale = len(actual) * (100 / 11)
        ax.plot(xk, yk * scale, color=COLORS["primary"], linewidth=1.8, alpha=0.9)

    if predicted and len(predicted) > 3:
        xk, yk = _kde_line(predicted, 0, 100, bandwidth=10)
        scale = len(predicted) * (100 / 11)
        ax.plot(xk, yk * scale, color=COLORS["accent2"], linewidth=1.8, alpha=0.9)

    ax.axvline(pass_threshold_pct, color=COLORS["alto"], linewidth=1.5, linestyle=":",
               alpha=0.7, label=f"Mínimo aprobado ({pass_threshold_pct:.0f}%)")

    ax.set_xlabel("Nota (%)", color=COLORS["text"])
    ax.set_ylabel("Número de alumnos", color=COLORS["text"])
    ax.set_title("Distribución: Notas Reales vs Predichas",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    ax.legend(facecolor=COLORS["bg_card"], edgecolor=COLORS["border"],
              labelcolor=COLORS["text"], fontsize=8)
    fig.tight_layout()
    return fig


def chart_risk_bubble(all_students: List[Dict], figsize=(8, 5), pass_threshold_pct: float = 50.0) -> Figure:
    """Plot engagement against grades with risk probability encoded as bubble size."""
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)

    risk_color_map = {
        "alto":  COLORS["alto"],
        "medio": COLORS["medio"],
        "bajo":  COLORS["bajo"],
    }

    has_data = False
    for s in all_students:
        m    = s.get("metrics", {})
        p    = s.get("prediction", {})
        eng  = m.get("engagement_score", 0)
        grade = m.get("final_grade_pct")
        if grade is None:
            continue
        has_data = True
        risk_prob = float(p.get("risk_probability", 0.1))
        risk      = s.get("risk_level", "bajo")
        color     = risk_color_map.get(risk, COLORS["neutral"])
        size      = max(30, risk_prob * 900)
        ax.scatter(eng, grade, s=size, c=color, alpha=0.72,
                   edgecolors=COLORS["bg"], linewidths=0.6, zorder=3)

    if not has_data:
        ax.text(0.5, 0.5, "Sin datos suficientes (se necesitan notas activas)",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=11)
        ax.set_title("Mapa de Riesgo: Engagement × Nota",
                     fontsize=11, fontweight="bold", color=COLORS["text"])
        fig.tight_layout()
        return fig

    # Reference lines.
    ax.axhline(pass_threshold_pct, color=COLORS["alto"],    linewidth=1.2, linestyle="--", alpha=0.5)
    ax.axvline(40, color=COLORS["neutral"], linewidth=1.0, linestyle="--", alpha=0.4)

    # Shade the critical zone
    ax.fill_between([0, 40], 0, pass_threshold_pct, color=COLORS["alto"], alpha=0.06)

    # Quadrant labels.
    fs = 7.5
    ax.text(2,  97, "Bajo eng. / Alta nota",     color=COLORS["fg_dim"], fontsize=fs)
    ax.text(42, 97, "✓ Engagement + nota alta",  color=COLORS["bajo"],   fontsize=fs)
    ax.text(2,   3, "⚠ ZONA CRÍTICA",            color=COLORS["alto"],   fontsize=fs, fontweight="bold")
    ax.text(42,  3, "Eng. ok · nota baja",        color=COLORS["medio"],  fontsize=fs)

    # Risk legend and size note
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", label="Riesgo alto",
               markerfacecolor=COLORS["alto"],  markersize=10),
        Line2D([0], [0], marker="o", color="w", label="Riesgo medio",
               markerfacecolor=COLORS["medio"], markersize=7),
        Line2D([0], [0], marker="o", color="w", label="Riesgo bajo",
               markerfacecolor=COLORS["bajo"],  markersize=5),
        Line2D([0], [0], linestyle="none", label="Tamaño ∝ prob. suspenso"),
    ]
    ax.legend(handles=legend_elements, facecolor=COLORS["bg_card"],
              edgecolor=COLORS["border"], labelcolor=COLORS["text"], fontsize=8)

    ax.set_xlabel("Engagement (0–100)", color=COLORS["text"])
    ax.set_ylabel("Nota actual (%)", color=COLORS["text"])
    ax.set_title("Mapa de Riesgo: Engagement × Nota × Prob. Suspenso",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    ax.set_xlim(-2, 102)
    ax.set_ylim(-2, 106)
    fig.tight_layout()
    return fig


def chart_all_courses_categories(courses: List[Dict], figsize=(6, 5)) -> Figure:
    """Plot course and enrollment distribution by category as a donut chart."""
    fig, ax = plt.subplots(figsize=figsize)
    _apply_dark_style(fig, ax)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    if not courses:
        ax.text(0.5, 0.5, "Sin cursos disponibles",
                transform=ax.transAxes, ha="center", va="center",
                color=COLORS["text"], fontsize=10)
        ax.set_title("Cursos por Categoría", fontsize=11, fontweight="bold",
                     color=COLORS["text"])
        return fig

    # Group by category
    cat_counts: Dict[str, int] = {}
    cat_students: Dict[str, int] = {}
    for c in courses:
        cat = str(c.get("categoryname") or c.get("category") or "Sin categoría")
        cat_counts[cat]   = cat_counts.get(cat, 0) + 1
        enroll = c.get("enrolledusercount")
        if enroll not in (None, "?", ""):
            cat_students[cat] = cat_students.get(cat, 0) + int(enroll)

    # Sort by course count and group small categories under "Other"
    sorted_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_cats) > 8:
        top = sorted_cats[:7]
        other_count = sum(v for _, v in sorted_cats[7:])
        other_students = sum(cat_students.get(k, 0) for k, _ in sorted_cats[7:])
        top.append(("Otras", other_count))
        cat_students["Otras"] = other_students
        sorted_cats = top

    labels = [k for k, _ in sorted_cats]
    values = [v for _, v in sorted_cats]
    total  = sum(values)

    # Varied color palette.
    palette = [
        COLORS["primary"], COLORS["accent"], COLORS["bajo"], COLORS["secondary"],
        COLORS["accent2"], COLORS["medio"], COLORS["alto"], COLORS["neutral"],
    ]
    colors = [palette[i % len(palette)] for i in range(len(labels))]

    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,
        autopct="%1.0f%%",
        colors=colors,
        startangle=90,
        pctdistance=0.80,
        wedgeprops={"linewidth": 2, "edgecolor": COLORS["bg"]},
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(7.5)
        at.set_fontweight("bold")

    # Agujero central
    circle = plt.Circle((0, 0), 0.54, color=COLORS["bg_card"])
    ax.add_patch(circle)
    ax.text(0,  0.10, str(total), ha="center", va="center",
            fontsize=24, fontweight="bold", color=COLORS["text"])
    ax.text(0, -0.12, "cursos", ha="center", va="center",
            fontsize=9, color=COLORS["fg_dim"])

    # Legend with course and student counts
    legend_labels = [
        f"{lbl}  ({cnt} cursos" +
        (f" · {cat_students[lbl]} al." if cat_students.get(lbl) else "") + ")"
        for lbl, cnt in zip(labels, values)
    ]
    ax.legend(
        wedges, legend_labels,
        loc="lower center", bbox_to_anchor=(0.5, -0.22),
        ncol=2, fontsize=7.5,
        facecolor=COLORS["bg_card"], labelcolor=COLORS["text"],
        framealpha=0.9,
    )
    ax.set_title("Distribución por Categoría",
                 fontsize=11, fontweight="bold", color=COLORS["text"])
    fig.tight_layout()
    return fig
