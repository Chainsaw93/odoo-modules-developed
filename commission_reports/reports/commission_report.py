# -*- coding: utf-8 -*-

from odoo import models, api
from collections import defaultdict
import operator

class CommissionReport(models.AbstractModel):
    _name = 'report.commission_reports.commission_report_template'
    _description = 'Reporte de Comisiones'

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepara los valores para el template del reporte"""
        
        if not data:
            return {}
            
        wizard = self.env['commission.report.wizard'].browse(data.get('wizard_id'))
        
        # Obtener las líneas del reporte
        domain = wizard._build_domain()
        lines = wizard._get_commission_lines(domain)
        
        # Aplicar agrupación si está configurada
        grouped_lines = self._apply_grouping(lines, data.get('grouping', []))
        
        # Calcular totales
        totals = self._calculate_totals(lines)
        
        return {
            'doc_ids': docids,
            'doc_model': 'commission.report.wizard',
            'docs': wizard,
            'data': data,
            'lines': lines,
            'grouped_lines': grouped_lines,
            'totals': totals,
            'company_name': data.get('company_name', ''),
            'date_from': data.get('date_from'),
            'date_to': data.get('date_to'),
            'filters': data.get('filters', ''),
            'has_grouping': bool(data.get('grouping')),
        }

    def _apply_grouping(self, lines, grouping_fields):
        """Aplica agrupación a las líneas del reporte"""
        if not grouping_fields:
            return {}
        
        grouped = defaultdict(list)
        
        for line in lines:
            # Crear clave de agrupación
            group_key = []
            for field in grouping_fields:
                value = line.get(field, '')
                # CORRECCIÓN: Asegurar que el valor sea string
                if value is False or value is None:
                    value = ''
                group_key.append(str(value))
            
            key = ' - '.join(group_key)
            grouped[key].append(line)
        
        # Ordenar grupos y calcular subtotales
        result = {}
        for group_name, group_lines in grouped.items():
            # Consolidar productos dentro del grupo (entre facturas)
            consolidated_group_lines = self._consolidate_group_lines(group_lines)
            
            # Ordenar líneas dentro del grupo - convertir fechas a string para evitar errores de tipo
            consolidated_group_lines.sort(key=lambda x: (str(x['date']), str(x['invoice'])))
            
            # Calcular subtotales del grupo
            subtotals = self._calculate_totals(consolidated_group_lines)
            
            result[group_name] = {
                'lines': consolidated_group_lines,
                'subtotals': subtotals
            }
        
        return result

    def _consolidate_group_lines(self, group_lines):
        """Consolida productos idénticos dentro de un grupo (entre facturas)"""
        consolidated = {}
        
        for line in group_lines:
            # CORRECCIÓN: Convertir todos los valores a string de forma segura
            code = line.get('code') or ''
            description = line.get('description') or ''
            currency = line.get('currency') or ''
            uom = line.get('uom') or ''
            
            # Clave de consolidación: producto + código
            # Remover indicador previo de consolidación si existe
            clean_description = description.split(' (Consolidado:')[0] if ' (Consolidado:' in description else description
            
            product_key = (
                str(code),
                str(clean_description),
                str(currency),
                str(uom)
            )
            
            if product_key not in consolidated:
                # Primera línea de este producto en el grupo
                consolidated[product_key] = {
                    'base_line': line.copy(),
                    'total_quantity': line.get('quantity', 0),
                    'total_cost_amount': line.get('total_cost', 0),
                    'total_net_amount': line.get('total_net', 0),
                    'total_benefit': line.get('benefit', 0),
                    'invoices': [str(line.get('invoice', ''))],
                    'dates': [str(line.get('date', ''))],
                    'lines_count': 1
                }
            else:
                # Consolidar con línea existente
                consolidated[product_key]['total_quantity'] += line.get('quantity', 0)
                consolidated[product_key]['total_cost_amount'] += line.get('total_cost', 0)
                consolidated[product_key]['total_net_amount'] += line.get('total_net', 0)
                consolidated[product_key]['total_benefit'] += line.get('benefit', 0)
                consolidated[product_key]['invoices'].append(str(line.get('invoice', '')))
                consolidated[product_key]['dates'].append(str(line.get('date', '')))
                consolidated[product_key]['lines_count'] += 1
        
        # Convertir a líneas consolidadas finales
        result = []
        for product_key, consolidated_data in consolidated.items():
            base_line = consolidated_data['base_line']
            total_quantity = consolidated_data['total_quantity']
            total_cost_amount = consolidated_data['total_cost_amount']
            total_net_amount = consolidated_data['total_net_amount']
            total_benefit = consolidated_data['total_benefit']
            
            # Recalcular valores promedio
            avg_cost = total_cost_amount / total_quantity if total_quantity > 0 else 0
            avg_price = total_net_amount / total_quantity if total_quantity > 0 else 0
            margin_percentage = (total_benefit / total_cost_amount * 100) if total_cost_amount > 0 else 0
            
            # Actualizar línea base con valores consolidados
            base_line.update({
                'quantity': total_quantity,
                'cost': avg_cost,
                'total_cost': total_cost_amount,
                'price': avg_price,
                'total_net': total_net_amount,
                'benefit': total_benefit,
                'margin_percentage': margin_percentage
            })
            
            # Agregar indicador de consolidación
            if consolidated_data['lines_count'] > 1:
                # CORRECCIÓN: Asegurar que description sea string
                original_desc = str(base_line.get('description', '')).split(' (Consolidado:')[0]
                unique_invoices = list(set(consolidated_data['invoices']))
                base_line['description'] = f"{original_desc} (Consolidado: {consolidated_data['lines_count']} líneas, {len(unique_invoices)} facturas)"
                
                # Para consolidación entre facturas, mostrar rango de fechas
                unique_dates = sorted(list(set(consolidated_data['dates'])))
                if len(unique_dates) > 1:
                    base_line['date'] = f"{unique_dates[0]} - {unique_dates[-1]}"
                    base_line['invoice'] = f"{len(unique_invoices)} facturas"
            
            result.append(base_line)
        
        return result

    def _calculate_totals(self, lines):
        """Calcula los totales del reporte"""
        totals = {
            'total_quantity': 0,
            'total_cost': 0,
            'total_net': 0,
            'total_benefit': 0,
            'avg_margin_percentage': 0,
            'line_count': len(lines)
        }
        
        if not lines:
            return totals
        
        for line in lines:
            totals['total_quantity'] += line.get('quantity', 0)
            totals['total_cost'] += line.get('total_cost', 0)
            totals['total_net'] += line.get('total_net', 0)
            totals['total_benefit'] += line.get('benefit', 0)
        
        # Calcular margen promedio
        if totals['total_cost'] > 0:
            totals['avg_margin_percentage'] = (totals['total_benefit'] / totals['total_cost']) * 100
        
        return totals


class CommissionExcelReport(models.AbstractModel):
    _name = 'report.commission_reports.commission_excel_report'
    _description = 'Reporte de Comisiones Excel'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizard):
        """Genera el reporte Excel"""
        
        # Obtener datos del reporte
        commission_report = self.env['report.commission_reports.commission_report_template']
        report_data = commission_report._get_report_values(None, data)
        
        # Crear hoja de trabajo
        sheet = workbook.add_worksheet('Reporte de Comisiones')
        
        # Definir formatos
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D7E4BC',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True
        })
        
        data_format = workbook.add_format({
            'border': 1,
            'valign': 'vcenter',
            'text_wrap': True
        })
        
        currency_format = workbook.add_format({
            'border': 1,
            'num_format': '#,##0.00',
            'valign': 'vcenter'
        })
        
        percentage_format = workbook.add_format({
            'border': 1,
            'num_format': '0.00%',
            'valign': 'vcenter'
        })
        
        # Configurar ancho de columnas
        column_widths = [20, 12, 15, 15, 15, 12, 25, 8, 8, 10, 12, 12, 12, 12, 12, 10]
        for i, width in enumerate(column_widths):
            sheet.set_column(i, i, width)
        
        row = 0
        
        # Título principal
        sheet.merge_range(row, 0, row, 15, 
                         f"{report_data['company_name']}", title_format)
        row += 1
        
        sheet.merge_range(row, 0, row, 15, 
                         "REPORTE DE COMISIONES", title_format)
        row += 1
        
        # Período
        sheet.merge_range(row, 0, row, 15, 
                         f"Período: Del {report_data['date_from']} hasta {report_data['date_to']}", 
                         header_format)
        row += 2
        
        # Filtros aplicados
        if report_data['filters']:
            sheet.merge_range(row, 0, row, 15, 
                             f"Filtros: {report_data['filters']}", data_format)
            row += 2
        
        # Encabezados
        headers = [
            'Cliente', 'Fecha', 'Factura', 'Número de Comprobante', 'Categoría', 'Código',
            'Descripción', 'Moneda', 'Unidad', 'Cantidad', 'Costo',
            'Costo Total', 'Precio', 'Total Neto', 'Beneficio', '% Margen Neto'
        ]
        
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        row += 1
        
        # Datos del reporte
        if report_data['has_grouping']:
            row = self._write_grouped_data(sheet, report_data['grouped_lines'], 
                                   data_format, currency_format, percentage_format, row, workbook)
        else:
            row = self._write_simple_data(sheet, report_data['lines'], 
                                        data_format, currency_format, percentage_format, row)
        
        # Totales
        row += 1
        totals = report_data['totals']
        
        sheet.write(row, 9, 'TOTALES:', header_format)
        sheet.write(row, 10, totals['total_quantity'], currency_format)
        sheet.write(row, 11, totals['total_cost'], currency_format)
        sheet.write(row, 12, '', data_format)
        sheet.write(row, 13, totals['total_net'], currency_format)
        sheet.write(row, 14, totals['total_benefit'], currency_format)
        sheet.write(row, 15, totals['avg_margin_percentage'] / 100, percentage_format)

    def _write_simple_data(self, sheet, lines, data_format, currency_format, percentage_format, start_row):
        """Escribe datos sin agrupación"""
        row = start_row
        
        for line in lines:
            # CORRECCIÓN: Convertir todos los valores a string de forma segura
            sheet.write(row, 0, str(line.get('customer', '')), data_format)
            sheet.write(row, 1, str(line.get('date', '')), data_format)
            sheet.write(row, 2, str(line.get('invoice', '')), data_format)
            sheet.write(row, 3, str(line.get('fiscal_receipt_number', '')), data_format)
            sheet.write(row, 4, str(line.get('category', '')), data_format)
            sheet.write(row, 5, str(line.get('code', '')), data_format)
            sheet.write(row, 6, str(line.get('description', '')), data_format)
            sheet.write(row, 7, str(line.get('currency', '')), data_format)
            sheet.write(row, 8, str(line.get('uom', '')), data_format)
            sheet.write(row, 9, line.get('quantity', 0), currency_format)
            sheet.write(row, 10, line.get('cost', 0), currency_format)
            sheet.write(row, 11, line.get('total_cost', 0), currency_format)
            sheet.write(row, 12, line.get('price', 0), currency_format)
            sheet.write(row, 13, line.get('total_net', 0), currency_format)
            sheet.write(row, 14, line.get('benefit', 0), currency_format)
            sheet.write(row, 15, line.get('margin_percentage', 0) / 100, percentage_format)
            row += 1
        
        return row

    def _write_grouped_data(self, sheet, grouped_lines, data_format, currency_format, percentage_format, start_row, workbook):
        """Escribe datos agrupados"""
        row = start_row
        
        for group_name, group_data in grouped_lines.items():
            # Encabezado del grupo
            sheet.merge_range(row, 0, row, 15, str(group_name), 
                             workbook.add_format({'bold': True, 'bg_color': '#E8F4F8'}))
            row += 1
            
            # Líneas del grupo
            row = self._write_simple_data(sheet, group_data['lines'], 
                                        data_format, currency_format, percentage_format, row)
            
            # Subtotales del grupo
            subtotals = group_data['subtotals']
            sheet.write(row, 9, 'Subtotal:', 
                       workbook.add_format({'bold': True, 'italic': True}))
            sheet.write(row, 10, subtotals['total_quantity'], currency_format)
            sheet.write(row, 11, subtotals['total_cost'], currency_format)
            sheet.write(row, 12, '', data_format)
            sheet.write(row, 13, subtotals['total_net'], currency_format)
            sheet.write(row, 14, subtotals['total_benefit'], currency_format)
            sheet.write(row, 15, subtotals['avg_margin_percentage'] / 100, percentage_format)
            row += 2
        
        return row