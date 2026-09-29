"""Compact UI for call-type attributes attached to taxonomy labels."""

from dash import dcc, html

from app.services.label_attributes import (
    human_label_attributes,
    label_attribute_options,
    model_label_attributes,
    selected_human_attribute_values,
)


def render_label_attribute_chips(item, label, *, include_human=True, include_model=True):
    records = []
    if include_model:
        records.extend(model_label_attributes(item, label))
    if include_human:
        records.extend(human_label_attributes(item, label))
    if not records:
        return None

    chips = []
    for record in records:
        is_model = record.get("source") == "model"
        source_name = "Machine-predicted call type" if is_model else "Human call-type annotation"
        icon = "bi bi-robot" if is_model else "bi bi-person-fill"
        score = record.get("score")
        score_text = f" {float(score):.0%}" if isinstance(score, (int, float)) else ""
        chips.append(
            html.Span(
                [
                    html.I(className=f"{icon} label-attribute-chip-icon", title=source_name),
                    html.Span(f'{record.get("display") or record.get("value")}{score_text}'),
                ],
                className=(
                    "label-attribute-chip label-attribute-chip--model"
                    if is_model
                    else "label-attribute-chip label-attribute-chip--human"
                ),
                title=f'{source_name}: {record.get("display") or record.get("value")}',
            )
        )
    return html.Div(chips, className="label-attribute-chips")


def build_label_attribute_control(item, label, *, item_id, editable, include_model=True):
    options = label_attribute_options(label)
    chips = render_label_attribute_chips(
        item,
        label,
        include_human=True,
        include_model=include_model,
    )
    if not options:
        return chips
    if not editable:
        return chips

    selected = selected_human_attribute_values(item, label)
    summary_text = "Edit call type" if selected else "+ Call type"
    editor = html.Details(
        [
            html.Summary(summary_text, className="label-attribute-editor-summary"),
            dcc.Checklist(
                id={"type": "modal-label-call-types", "item_id": item_id, "label": label},
                options=[{"label": option["display"], "value": option["value"]} for option in options],
                value=selected,
                inline=True,
                className="label-attribute-checklist",
                inputClassName="label-attribute-check-input",
                labelClassName="label-attribute-check-label",
            ),
        ],
        className="label-attribute-editor",
    )
    return html.Div([chips, editor], className="label-attribute-control")
