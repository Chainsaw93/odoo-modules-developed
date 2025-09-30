# -*- coding: utf-8 -*-
import base64
from io import BytesIO
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError

import xlsxwriter  # suponiendo que xlsxwriter esté instalado en el entorno


class WizardVentasAuditoria(models.TransientModel):
    _name = "wizard.ventas.auditoria"
    _description = "Wizard para Reporte de Ventas Auditoría"

    date_from = fields.Date(string="Fecha Desde", required=True)
    date_to = fields.Date(string="Fecha Hasta", required=True)

    xlsx_file = fields.Binary(string="Archivo Excel", readonly=True)
    xlsx_filename = fields.Char(string="Nombre del Archivo", readonly=True)

    @api.constrains("date_from", "date_to")
    def _check_fechas(self):
        for rec in self:
            if (
                rec.date_from and rec.date_to
                and rec.date_from > rec.date_to
            ):
                raise UserError(
                    _("La fecha Desde no puede ser mayor que la fecha Hasta.")
                )

    def action_print_pdf(self):
        data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
        }
        return (
            self.env.ref(
                'sales_auditoria_report.action_report_ventas_auditoria_pdf'
            ).report_action(self, data=data)
        )

    def action_generate_xlsx(self):
        if not self.date_from or not self.date_to:
            raise UserError(_("Debes especificar Fecha Desde y Fecha Hasta."))

        domain = [
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('state', 'not in', ['draft', 'cancel']),
        ]
        invoices = self.env['account.move'].search(
            domain,
            order='invoice_date, name',
        )

        order_map = {
            'Credito Fiscal': 1,
            'Notas de Credito': 2,
            'Factura Gubernamental': 3,
            'Factura Régimen Especial': 4,
            'Pesos(Conversion)': 5,
        }
        grouped = {}
        moneda_objetivo = self.env.ref('base.DOP')

        for inv in invoices:
            receipt_type = getattr(inv, 'l10n_do_at_receipt_type', False)
            if receipt_type:
                tipo_name = getattr(receipt_type, 'name', False) or receipt_type.display_name
            else:
                tipo_name = 'Otros'
            if tipo_name not in grouped:
                grouped[tipo_name] = {
                    'tipo': tipo_name,
                    'lines': [],
                    'subtotal': 0.0,
                    'subtotal_ingreso_neto': 0.0,
                    'subtotal_itbis': 0.0,
                }
            imp_nincluidos = inv.amount_untaxed_in_currency_signed
            impuesto = inv.amount_tax_signed
            total = inv.amount_total_in_currency_signed

            if inv.currency_id != moneda_objetivo:
                imp_nincluidos = inv.currency_id._convert(
                    imp_nincluidos,
                    moneda_objetivo,
                    inv.company_id,
                    inv.invoice_date,
                )
                total = inv.currency_id._convert(
                    total,
                    moneda_objetivo,
                    inv.company_id,
                    inv.invoice_date,
                )
            if inv.company_currency_id != moneda_objetivo:
                impuesto = inv.company_currency_id._convert(
                    impuesto,
                    moneda_objetivo,
                    inv.company_id,
                    inv.invoice_date,
                )

            grouped[tipo_name]['lines'].append({
                'numero_factura': inv.name,
                'fecha_factura': inv.invoice_date,
                'cliente': inv.invoice_partner_display_name,
                'imp_nincluidos': imp_nincluidos,
                'impuesto': impuesto,
                'total': total,
                'numero_comprobante': (
                    inv.l10n_do_at_fiscal_receipt_number or inv.name
                ),
            })
            grouped[tipo_name]['subtotal'] += total
            grouped[tipo_name]['subtotal_ingreso_neto'] += imp_nincluidos
            grouped[tipo_name]['subtotal_itbis'] += impuesto

        ordered_grouped = []
        for tipo_key, values in grouped.items():
            rank = order_map.get(tipo_key, 999)
            ordered_grouped.append((rank, values))
        ordered_grouped.sort(key=lambda x: x[0])
        grouped_data = [grp[1] for grp in ordered_grouped]

        total_general_ingreso_neto = sum(
            g['subtotal_ingreso_neto'] for g in grouped_data
        )
        total_general_itbis = sum(g['subtotal_itbis'] for g in grouped_data)
        total_general_total = sum(g['subtotal'] for g in grouped_data)

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        bold = workbook.add_format({'bold': True})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})

        sheet = workbook.add_worksheet("Ventas Auditoría")
        row = 0

        sheet.write(row, 0, "REPORTE DE VENTAS AUDITORES", bold)
        row += 1
        sheet.write(
            row,
            6,
            f"Período: {self.date_from} - {self.date_to}",
        )
        row += 1
        sheet.write(row, 6, "Moneda: Pesos (RD)")
        row += 2

        headers = [
            "No. Factura", "Fecha", "Cliente",
            "Ingreso Neto", "ITBIS", "Total",
            "NCF"
        ]
        for col, header in enumerate(headers):
            sheet.write(row, col, header, bold)
        row += 1

        for group in grouped_data:
            sheet.write(row, 0, group['tipo'], bold)
            row += 1
            for line in group['lines']:
                sheet.write(row, 0, line['numero_factura'])
                sheet.write_datetime(
                    row, 1,
                    datetime.strptime(str(line['fecha_factura']), "%Y-%m-%d"),
                    date_format
                )
                sheet.write(row, 2, line['cliente'])
                sheet.write_number(row, 3, line['imp_nincluidos'])
                sheet.write_number(row, 4, line['impuesto'])
                sheet.write_number(row, 5, line['total'])
                sheet.write(row, 6, line['numero_comprobante'])
                row += 1

            sheet.write(row, 2, "Subtotal:", bold)
            sheet.write_number(row, 3, group['subtotal_ingreso_neto'], bold)
            sheet.write_number(row, 4, group['subtotal_itbis'], bold)
            sheet.write_number(row, 5, group['subtotal'], bold)
            row += 2

        sheet.write(row, 2, "TOTAL GENERAL", bold)
        sheet.write_number(row, 3, total_general_ingreso_neto, bold)
        sheet.write_number(row, 4, total_general_itbis, bold)
        sheet.write_number(row, 5, total_general_total, bold)
        row += 2

        sheet.set_column(0, 0, 15)
        sheet.set_column(1, 1, 15)
        sheet.set_column(2, 2, 30)
        sheet.set_column(3, 5, 18)
        sheet.set_column(6, 6, 25)

        workbook.close()
        output.seek(0)
        data = output.read()

        filename = "Reporte_Ventas_Auditoria_%s_%s.xlsx" % (
            self.date_from,
            self.date_to,
        )
        self.xlsx_file = base64.b64encode(data)
        self.xlsx_filename = filename

        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=wizard.ventas.auditoria"
                "&id=%s&field=xlsx_file&filename_field=xlsx_filename"
                "&download=true&filename=%s" % (self.id, filename)
            ),
            "target": "self",
        }

    def action_open_download(self):
        if not self.xlsx_file or not self.xlsx_filename:
            raise UserError(_("Primero debes generar el Excel."))
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=wizard.ventas.auditoria"
                "&id=%s&field=xlsx_file&filename_field=xlsx_filename"
                "&download=true&filename=%s" % (self.id, self.xlsx_filename)
            ),
            "target": "self",
        }


class ReportVentasAuditoria(models.AbstractModel):
    _name = "report.sales_auditoria_report.report_sales_auditoria_pdf"
    _description = "Reporte QWeb PDF para Ventas Auditoría"

    @api.model
    def _get_report_values(self, docids, data=None):
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        if not date_from or not date_to:
            raise UserError(
                _(
                    "Debe especificar un rango de fechas para generar "
                    "el reporte."
                )
            )

        domain = [
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('state', 'not in', ['draft', 'cancel']),
        ]
        invoices = self.env['account.move'].search(
            domain,
            order='invoice_date, name',
        )

        order_map = {
            'Credito Fiscal': 1,
            'Notas de Credito': 2,
            'Factura Gubernamental': 3,
            'Factura Régimen Especial': 4,
            'Pesos(Conversion)': 5,
        }

        grouped = {}
        moneda_objetivo = self.env.ref('base.DOP')

        for inv in invoices:
            receipt_type = getattr(inv, 'l10n_do_at_receipt_type', False)
            if receipt_type:
                tipo_name = getattr(receipt_type, 'name', False) or receipt_type.display_name
            else:
                tipo_name = 'Otros'
            if tipo_name not in grouped:
                grouped[tipo_name] = {
                    'tipo': tipo_name,
                    'lines': [],
                    'subtotal': 0.0,
                    'subtotal_ingreso_neto': 0.0,
                    'subtotal_itbis': 0.0,
                }
            imp_nincluidos = inv.amount_untaxed_in_currency_signed
            impuesto = inv.amount_tax_signed
            total = inv.amount_total_in_currency_signed

            if inv.currency_id != moneda_objetivo:
                imp_nincluidos = inv.currency_id._convert(
                    imp_nincluidos,
                    moneda_objetivo,
                    inv.company_id,
                    inv.invoice_date,
                )
                total = inv.currency_id._convert(
                    total,
                    moneda_objetivo,
                    inv.company_id,
                    inv.invoice_date,
                )
            if inv.company_currency_id != moneda_objetivo:
                impuesto = inv.company_currency_id._convert(
                    impuesto,
                    moneda_objetivo,
                    inv.company_id,
                    inv.invoice_date,
                )

            grouped[tipo_name]['lines'].append({
                'numero_factura': inv.name,
                'fecha_factura': inv.invoice_date.strftime('%Y-%m-%d'),
                'cliente': inv.invoice_partner_display_name,
                'imp_nincluidos': "{:,.2f}".format(imp_nincluidos),
                'impuesto': "{:,.2f}".format(impuesto),
                'total': "{:,.2f}".format(total),
                'numero_comprobante': (
                    inv.l10n_do_at_fiscal_receipt_number or inv.name
                ),
            })
            grouped[tipo_name]['subtotal'] += total
            grouped[tipo_name]['subtotal_ingreso_neto'] += imp_nincluidos
            grouped[tipo_name]['subtotal_itbis'] += impuesto

        ordered_grouped = []
        for tipo_key, values in grouped.items():
            rank = order_map.get(tipo_key, 999)
            ordered_grouped.append((rank, values))
        ordered_grouped.sort(key=lambda x: x[0])
        grouped_data = [grp[1] for grp in ordered_grouped]

        total_general_ingreso_neto = sum(
            g['subtotal_ingreso_neto'] for g in grouped_data
        )
        total_general_itbis = sum(g['subtotal_itbis'] for g in grouped_data)
        total_general_total = sum(g['subtotal'] for g in grouped_data)

        currency_name = moneda_objetivo.name or 'DOP'

        return {
            'doc_ids': docids,
            'doc_model': 'wizard.ventas.auditoria',
            'data': data,
            'date_from': date_from,
            'date_to': date_to,
            'currency_name': currency_name,
            'grouped_data': grouped_data,
            'total_general_ingreso_neto': "{:,.2f}".format(total_general_ingreso_neto),
            'total_general_itbis': "{:,.2f}".format(total_general_itbis),
            'total_general_total': "{:,.2f}".format(total_general_total),
        }
