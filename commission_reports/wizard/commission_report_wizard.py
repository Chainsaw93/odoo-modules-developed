# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import date

class CommissionReportWizard(models.TransientModel):
    _name = 'commission.report.wizard'
    _description = 'Wizard para Reporte de Comisiones'

    # Filtros principales
    date_from = fields.Date(
        string='Fecha Inicio',
        required=True,
        default=lambda self: date.today().replace(day=1)
    )
    date_to = fields.Date(
        string='Fecha Fin',
        required=True,
        default=fields.Date.today
    )
    
    # Filtros con selección múltiple
    salesperson_ids = fields.Many2many(
        'res.users',
        string='Vendedores',
        domain=[('share', '=', False)]
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Clientes',
        domain=[('is_company', '=', True), ('customer_rank', '>', 0)]
    )
    category_ids = fields.Many2many(
        'product.category',
        string='Categorías'
    )
    product_ids = fields.Many2many(
        'product.product',
        string='Productos'
    )
    
    # Campo corregido para facturas
    invoice_ids = fields.Many2many(
        'account.move',
        string='Facturas',
        domain=[('move_type', 'in', ['out_invoice', 'out_refund']), ('state', '=', 'posted')]
    )
    
    company_ids = fields.Many2many(
        'res.company',
        string='Sucursales'
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Almacenes'
    )
    
    # Opciones de agrupación
    group_by_salesperson = fields.Boolean(string='Agrupar por Vendedor')
    group_by_customer = fields.Boolean(string='Agrupar por Cliente')
    group_by_category = fields.Boolean(string='Agrupar por Categoría')
    group_by_product = fields.Boolean(string='Agrupar por Producto')
    group_by_company = fields.Boolean(string='Agrupar por Sucursal')
    group_by_warehouse = fields.Boolean(string='Agrupar por Almacén')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'company_ids' in fields:
            res['company_ids'] = [(6, 0, [self.env.company.id])]
        return res

    def generate_report(self):
        """Genera el reporte con los filtros aplicados"""
        data = self._prepare_report_data()
        
        return {
            'type': 'ir.actions.report',
            'report_name': 'commission_reports.commission_report_template',
            'report_type': 'qweb-pdf',
            'data': data,
            'context': self.env.context,
        }

    def generate_excel_report(self):
        """Genera el reporte en formato Excel"""
        data = self._prepare_report_data()
        
        return {
            'type': 'ir.actions.report',
            'report_name': 'commission_reports.commission_excel_report',
            'report_type': 'xlsx',
            'data': data,
            'context': self.env.context,
        }

    def _prepare_report_data(self):
        """Prepara los datos para el reporte"""
        domain = self._build_domain()
        lines = self._get_commission_lines(domain)
        
        return {
            'wizard_id': self.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_name': self.env.company.name,
            'lines': lines,
            'filters': self._get_filter_description(),
            'grouping': self._get_grouping_fields()
        }

    def _build_domain(self):
        """Construye el dominio para filtrar las facturas"""
        domain = [
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '=', 'posted'),
        ]
        
        # Si se seleccionan facturas específicas, usar solo esas (ignorar filtros de fecha)
        if self.invoice_ids:
            domain.append(('id', 'in', self.invoice_ids.ids))
        else:
            # Solo aplicar filtros de fecha si no hay facturas específicas
            domain.extend([
                ('invoice_date', '>=', self.date_from),
                ('invoice_date', '<=', self.date_to),
            ])
        
        if self.salesperson_ids:
            domain.append(('invoice_user_id', 'in', self.salesperson_ids.ids))
        
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
            
        if self.company_ids:
            domain.append(('company_id', 'in', self.company_ids.ids))
        
        return domain

    def _get_commission_lines(self, domain):
        """Obtiene las líneas del reporte de comisiones"""
        invoices = self.env['account.move'].search(domain)
        lines = []
        
        for invoice in invoices:
            consolidated_lines = self._consolidate_invoice_lines(invoice)
            lines.extend(consolidated_lines)
        
        return lines

    def _consolidate_invoice_lines(self, invoice):
        """Consolida múltiples líneas del mismo producto en una factura"""
        consolidated = {}
        
        for line in invoice.invoice_line_ids:
            if not self._line_matches_filters(line):
                continue
                
            product = line.product_id
            key = product.id
            
            if key not in consolidated:
                consolidated[key] = {
                    'invoice': invoice,
                    'product': product,
                    'lines': [line],
                    'total_quantity': line.quantity,
                    'total_subtotal': line.price_subtotal,
                    'lines_count': 1
                }
            else:
                consolidated[key]['lines'].append(line)
                consolidated[key]['total_quantity'] += line.quantity
                consolidated[key]['total_subtotal'] += line.price_subtotal
                consolidated[key]['lines_count'] += 1
        
        result = []
        for key, consolidated_line in consolidated.items():
            commission_line = self._prepare_consolidated_commission_line(consolidated_line)
            result.append(commission_line)
        
        return result

    def _prepare_consolidated_commission_line(self, consolidated_line):
        """Prepara una línea consolidada del reporte de comisiones"""
        invoice = consolidated_line['invoice']
        product = consolidated_line['product']
        quantity = consolidated_line['total_quantity']
        total_net = consolidated_line['total_subtotal']
        
        unit_price = total_net / quantity if quantity > 0 else 0.0
        cost_price = self._get_real_product_cost(product, invoice.invoice_date, quantity)
        
        total_cost = cost_price * quantity
        benefit = total_net - total_cost
        margin_percentage = (benefit / total_net * 100) if total_net > 0 else 0
        
        warehouse = self._get_line_warehouse(invoice, None)
        
        # CORRECCIÓN: Asegurar que todos los valores de texto sean strings
        product_name = product.name or ''
        category_name = product.categ_id.name if product.categ_id else ''
        product_code = product.default_code or ''
        partner_name = invoice.partner_id.name or ''
        invoice_name = invoice.name or ''
        fiscal_receipt = invoice.l10n_do_at_fiscal_receipt_number or ''
        currency_name = invoice.currency_id.name or ''
        uom_name = product.uom_id.name or ''
        salesperson_name = invoice.invoice_user_id.name if invoice.invoice_user_id else ''
        company_name = invoice.company_id.name or ''
        warehouse_name = warehouse or ''
        
        description = product_name
        if consolidated_line['lines_count'] > 1:
            description += f" (Consolidado: {consolidated_line['lines_count']} líneas)"
        
        return {
            'customer': partner_name,
            'date': invoice.invoice_date,
            'invoice': invoice_name,
            'fiscal_receipt_number': fiscal_receipt,
            'category': category_name,
            'code': product_code,
            'description': description,
            'currency': currency_name,
            'uom': uom_name,
            'quantity': quantity,
            'cost': cost_price,
            'total_cost': total_cost,
            'price': unit_price,
            'total_net': total_net,
            'benefit': benefit,
            'margin_percentage': margin_percentage,
            'salesperson': salesperson_name,
            'company': company_name,
            'warehouse': warehouse_name,
        }

    def _line_matches_filters(self, line):
        """Verifica si la línea coincide con los filtros adicionales"""
        if self.category_ids and line.product_id.categ_id not in self.category_ids:
            return False
            
        if self.product_ids and line.product_id not in self.product_ids:
            return False
            
        if self.warehouse_ids:
            picking = self.env['stock.picking'].search([
                ('origin', '=', line.move_id.name),
                ('state', '=', 'done')
            ], limit=1)
            if picking and picking.location_id.warehouse_id not in self.warehouse_ids:
                return False
        
        return True

    def _get_real_product_cost(self, product, invoice_date, quantity):
        """Obtiene el costo real del producto según su método de valoración"""
        
        if product.cost_method == 'standard':
            return product.standard_price
        
        if product.cost_method in ['fifo', 'average']:
            stock_moves = self.env['stock.move'].search([
                ('product_id', '=', product.id),
                ('date', '<=', invoice_date),
                ('state', '=', 'done'),
                ('location_dest_id.usage', '=', 'internal'),
            ], order='date desc', limit=10)
            
            if stock_moves:
                valuation_layers = self.env['stock.valuation.layer'].search([
                    ('stock_move_id', 'in', stock_moves.ids),
                    ('product_id', '=', product.id)
                ], order='create_date desc')
                
                if valuation_layers:
                    if product.cost_method == 'fifo':
                        latest_layer = valuation_layers[0]
                        if latest_layer.quantity and latest_layer.quantity != 0:
                            return abs(latest_layer.value / latest_layer.quantity)
                    
                    elif product.cost_method == 'average':
                        total_value = sum(layer.value for layer in valuation_layers[:5])
                        total_qty = sum(layer.quantity for layer in valuation_layers[:5] if layer.quantity > 0)
                        
                        if total_qty and total_qty != 0:
                            return abs(total_value / total_qty)
        
        return product.standard_price or 0.0

    def _get_line_warehouse(self, invoice, line):
        """Obtiene el almacén de una línea de factura"""
        picking = self.env['stock.picking'].search([
            ('origin', '=', invoice.name),
            ('state', '=', 'done')
        ], limit=1)
        
        if picking and picking.location_id.warehouse_id:
            return picking.location_id.warehouse_id.name
        
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', invoice.company_id.id)
        ], limit=1)
        
        return warehouse.name if warehouse else ''

    def _get_filter_description(self):
        """Obtiene la descripción de los filtros aplicados"""
        filters = []
        
        if self.salesperson_ids:
            filters.append(f"Vendedores: {', '.join(self.salesperson_ids.mapped('name'))}")
        
        if self.partner_ids:
            filters.append(f"Clientes: {', '.join(self.partner_ids.mapped('name'))}")
        
        if self.category_ids:
            filters.append(f"Categorías: {', '.join(self.category_ids.mapped('name'))}")
        
        if self.product_ids:
            filters.append(f"Productos: {', '.join(self.product_ids.mapped('name'))}")
        
        if self.company_ids:
            filters.append(f"Sucursales: {', '.join(self.company_ids.mapped('name'))}")
        
        if self.warehouse_ids:
            filters.append(f"Almacenes: {', '.join(self.warehouse_ids.mapped('name'))}")
        
        if self.invoice_ids:
            filters.append(f"Facturas: {', '.join(self.invoice_ids.mapped('name'))}")
        
        return '; '.join(filters) if filters else 'Sin filtros adicionales'

    def _get_grouping_fields(self):
        """Obtiene los campos de agrupación activos"""
        grouping = []
        
        if self.group_by_salesperson:
            grouping.append('salesperson')
        if self.group_by_customer:
            grouping.append('customer')
        if self.group_by_category:
            grouping.append('category')
        if self.group_by_product:
            grouping.append('description')
        if self.group_by_company:
            grouping.append('company')
        if self.group_by_warehouse:
            grouping.append('warehouse')
        
        return grouping