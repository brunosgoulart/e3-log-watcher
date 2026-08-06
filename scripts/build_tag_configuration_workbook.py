from __future__ import annotations

from pathlib import Path

import xlsxwriter
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "phase1.yaml"
OUTPUT_PATH = ROOT / "outputs" / "tag_configuration" / "configuracao_tags_e3.xlsx"


def load_rows() -> list[dict[str, str]]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    catalog = config["metric_catalog"]
    groups = config["server_groups"]
    rows: list[dict[str, str]] = []
    for tag in config["authorized_tags"]:
        group = next(item for item in groups if tag.startswith(f"{item['pi_prefix']}"))
        suffix = tag.removeprefix(f"{group['pi_prefix']}.")
        definition = catalog[suffix]
        rows.append(
            {
                "group_id": group["group_id"],
                "servers": "/".join(group["physical_servers"]),
                "tag": tag,
                "suffix": suffix,
                "category": definition["category"],
                "expected_type": definition["expected_type"],
            }
        )
    return rows


def build_workbook(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(OUTPUT_PATH)
    workbook.set_properties(
        {
            "title": "Configuração de tags E3",
            "subject": "Unidades, faixas de atenção/críticas e prioridades de alarme",
            "author": "E3 Predictive Monitor",
        }
    )

    navy = "#17365D"
    blue = "#D9EAF7"
    yellow = "#FFF2CC"
    gray = "#E7E6E6"
    green = "#E2F0D9"
    red = "#FCE4D6"
    header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": navy, "align": "center", "valign": "vcenter", "border": 0, "text_wrap": True})
    title = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": navy, "font_size": 16, "align": "left", "valign": "vcenter"})
    subtitle = workbook.add_format({"font_color": "#1F1F1F", "bg_color": blue, "italic": True, "text_wrap": True, "valign": "vcenter"})
    readonly = workbook.add_format({"bg_color": "#F8FAFC", "font_color": "#404040"})
    input_text = workbook.add_format({"bg_color": yellow, "font_color": "#000000"})
    input_number = workbook.add_format({"bg_color": yellow, "font_color": "#000000", "num_format": "#,##0.######"})
    not_applicable = workbook.add_format({"bg_color": gray, "font_color": "#666666", "align": "center"})
    status = workbook.add_format({"font_color": "#404040"})
    section = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": navy, "align": "left"})
    note = workbook.add_format({"text_wrap": True, "valign": "top"})
    kpi_label = workbook.add_format({"bold": True, "bg_color": blue})
    kpi_value = workbook.add_format({"bold": True, "font_size": 13, "align": "center", "bg_color": "#F8FAFC", "border": 1, "border_color": "#B7C9D6"})

    config_sheet = workbook.add_worksheet("Configuração de Tags")
    config_sheet.hide_gridlines(2)
    config_sheet.freeze_panes(1, 3)
    config_sheet.set_landscape()
    config_sheet.fit_to_pages(1, 0)
    config_sheet.set_tab_color(navy)
    headers = [
        "Grupo lógico",
        "Servidores físicos",
        "Tag PI",
        "Métrica",
        "Categoria",
        "Tipo esperado",
        "Unidade de medida",
        "Limite normal inferior",
        "Limite normal superior",
        "Atenção inferior",
        "Atenção superior",
        "Crítico inferior",
        "Crítico superior",
        "Prioridade",
        "Direção do alarme",
        "Persistência (amostras)",
        "Observações",
        "Situação",
    ]
    config_sheet.set_row(0, 34)
    config_sheet.write_row(0, 0, headers, header)
    widths = [15, 24, 43, 30, 15, 14, 20, 18, 18, 16, 16, 16, 16, 13, 19, 19, 35, 26]
    for column, width in enumerate(widths):
        config_sheet.set_column(column, column, width)

    for row_index, item in enumerate(rows, start=1):
        excel_row = row_index + 1
        config_sheet.set_row(row_index, 22)
        config_sheet.write(row_index, 0, item["group_id"], readonly)
        config_sheet.write(row_index, 1, item["servers"], readonly)
        config_sheet.write(row_index, 2, item["tag"], readonly)
        config_sheet.write(row_index, 3, item["suffix"], readonly)
        config_sheet.write(row_index, 4, item["category"], readonly)
        config_sheet.write(row_index, 5, item["expected_type"], readonly)
        config_sheet.write_blank(row_index, 6, None, input_text)
        if item["expected_type"] == "number":
            for column in range(7, 13):
                config_sheet.write_blank(row_index, column, None, input_number)
            config_sheet.write_blank(row_index, 13, None, input_text)
            config_sheet.write(row_index, 14, "Aumento", input_text)
            config_sheet.write_blank(row_index, 15, None, input_number)
            formula = (
                f'=IF(G{excel_row}="","PENDENTE: unidade",'
                f'IF(OR(H{excel_row}="",I{excel_row}="",J{excel_row}="",K{excel_row}="",L{excel_row}="",M{excel_row}=""),'
                f'"PENDENTE: faixas",IF(N{excel_row}="","PENDENTE: prioridade","PRONTO")))'
            )
        else:
            for column in range(7, 13):
                config_sheet.write(row_index, column, "N/A", not_applicable)
            config_sheet.write(row_index, 13, "N/A", not_applicable)
            config_sheet.write(row_index, 14, "Não aplicável", not_applicable)
            config_sheet.write(row_index, 15, "N/A", not_applicable)
            formula = '="REVISAR: tipo não numérico"'
        config_sheet.write_blank(row_index, 16, None, input_text)
        config_sheet.write_formula(row_index, 17, formula, status)

    last_row = len(rows) + 1
    config_sheet.autofilter(0, 0, last_row - 1, len(headers) - 1)
    config_sheet.data_validation(1, 13, last_row - 1, 13, {"validate": "list", "source": ["Crítica", "Alta", "Média", "Baixa"]})
    config_sheet.data_validation(1, 14, last_row - 1, 14, {"validate": "list", "source": ["Aumento", "Queda", "Ambos", "Não aplicável"]})
    config_sheet.data_validation(1, 15, last_row - 1, 15, {"validate": "integer", "criteria": "between", "minimum": 1, "maximum": 100})
    config_sheet.conditional_format(1, 17, last_row - 1, 17, {"type": "text", "criteria": "containing", "value": "PRONTO", "format": workbook.add_format({"bg_color": green, "font_color": "#006100"})})
    config_sheet.conditional_format(1, 17, last_row - 1, 17, {"type": "text", "criteria": "containing", "value": "PENDENTE", "format": workbook.add_format({"bg_color": yellow, "font_color": "#9C5700"})})
    config_sheet.conditional_format(1, 17, last_row - 1, 17, {"type": "text", "criteria": "containing", "value": "REVISAR", "format": workbook.add_format({"bg_color": red, "font_color": "#9C0006"})})
    config_sheet.conditional_format(1, 13, last_row - 1, 13, {"type": "text", "criteria": "containing", "value": "Crítica", "format": workbook.add_format({"bg_color": red, "font_color": "#9C0006", "bold": True})})

    summary = workbook.add_worksheet("Resumo")
    summary.hide_gridlines(2)
    summary.set_landscape()
    summary.fit_to_pages(1, 1)
    summary.set_tab_color("#4F81BD")
    summary.set_column("A:A", 35)
    summary.set_column("B:B", 18)
    summary.set_column("D:D", 30)
    summary.set_column("E:E", 18)
    summary.merge_range("A1:E1", "Configuração operacional das tags E3", title)
    summary.merge_range("A2:E2", "Preencha os campos amarelos na aba 'Configuração de Tags'. A situação é atualizada por fórmula.", subtitle)
    summary.write("A4", "Indicador", section)
    summary.write("B4", "Quantidade", section)
    summary.write("A5", "Tags autorizadas", kpi_label)
    summary.write_formula("B5", "=COUNTA('Configuração de Tags'!$C$2:$C$76)", kpi_value)
    summary.write("A6", "Tags prontas", kpi_label)
    summary.write_formula("B6", "=COUNTIF('Configuração de Tags'!$R$2:$R$76,\"PRONTO\")", kpi_value)
    summary.write("A7", "Unidade pendente", kpi_label)
    summary.write_formula("B7", "=COUNTIF('Configuração de Tags'!$R$2:$R$76,\"PENDENTE: unidade\")", kpi_value)
    summary.write("A8", "Faixas pendentes", kpi_label)
    summary.write_formula("B8", "=COUNTIF('Configuração de Tags'!$R$2:$R$76,\"PENDENTE: faixas\")", kpi_value)
    summary.write("A9", "Prioridade pendente", kpi_label)
    summary.write_formula("B9", "=COUNTIF('Configuração de Tags'!$R$2:$R$76,\"PENDENTE: prioridade\")", kpi_value)
    summary.write("D4", "Prioridade", section)
    summary.write("E4", "Quantidade", section)
    for index, priority in enumerate(("Crítica", "Alta", "Média", "Baixa"), start=5):
        summary.write(index - 1, 3, priority, kpi_label)
        summary.write_formula(index - 1, 4, f'=COUNTIF(\'Configuração de Tags\'!$N$2:$N$76,"{priority}")', kpi_value)
    summary.merge_range("A12:E12", "Critérios de preenchimento", section)
    guidance = [
        "1. Confirme a unidade de medida de cada tag numérica.",
        "2. Informe a faixa normal e as faixas de atenção/crítica aprovadas pela operação.",
        "3. Defina a prioridade e a direção: aumento, queda ou ambos.",
        "4. Escolha a persistência mínima em amostras antes de abrir um alarme.",
        "5. Tags textuais ou de status foram marcadas como 'REVISAR' e exigem regra semântica, não faixa numérica.",
        "6. Esta planilha define limites operacionais; ela não substitui a baseline estatística dinâmica do sistema.",
    ]
    for index, text in enumerate(guidance, start=13):
        summary.merge_range(index - 1, 0, index - 1, 4, text, note)
        summary.set_row(index - 1, 24)

    instructions = workbook.add_worksheet("Instruções")
    instructions.hide_gridlines(2)
    instructions.set_landscape()
    instructions.fit_to_pages(1, 1)
    instructions.print_area("A1:B13")
    instructions.set_tab_color("#70AD47")
    instructions.set_column("A:A", 28)
    instructions.set_column("B:B", 100)
    instructions.merge_range("A1:B1", "Como parametrizar os alarmes", title)
    instructions.write_row("A3", ["Campo", "Orientação"], header)
    definitions = [
        ("Unidade de medida", "Informe a unidade confirmada no PI ou na documentação operacional. Ex.: %, MB, ms, eventos/min."),
        ("Faixa normal", "Intervalo de operação esperado. Ajuda a interpretar o desvio, mas não substitui a baseline dinâmica por sessão."),
        ("Atenção", "Faixa que exige acompanhamento. Use os dois limites quando desvios para cima e para baixo forem relevantes."),
        ("Crítico", "Faixa que demanda ação imediata ou escalonamento. Deve ser aprovada pela operação responsável."),
        ("Prioridade", "Crítica, Alta, Média ou Baixa. A prioridade define a relevância do sinal, não a severidade calculada automaticamente."),
        ("Direção do alarme", "Aumento para métricas que degradam ao subir; Queda para métricas que degradam ao cair; Ambos para os dois casos."),
        ("Persistência", "Número de amostras consecutivas fora da faixa antes do alarme. Deve considerar o intervalo de coleta de 60 segundos."),
        ("Observações", "Registre exceções, períodos de manutenção, picos esperados ou a fonte da decisão operacional."),
    ]
    for row, definition in enumerate(definitions, start=3):
        instructions.write(row, 0, definition[0], kpi_label)
        instructions.write(row, 1, definition[1], note)
        instructions.set_row(row, 38)
    instructions.merge_range("A13:B13", f"Fonte: {CONFIG_PATH.relative_to(ROOT).as_posix()} | Gerado a partir da allow-list vigente de {len(rows)} tags.", subtitle)

    workbook.close()


if __name__ == "__main__":
    build_workbook(load_rows())
