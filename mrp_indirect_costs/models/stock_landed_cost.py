from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'
    
    production_id = fields.Many2one(
        'mrp.production',
        string='Orden de Fabricación',
        compute='_compute_production_id',
        store=True
    )
    
    @api.depends('mrp_production_ids')
    def _compute_production_id(self):
        """Computar orden de fabricación si solo hay una"""
        for record in self:
            if len(record.mrp_production_ids) == 1:
                record.production_id = record.mrp_production_ids[0]
            else:
                record.production_id = False
    
    def compute_landed_cost(self):
        """Override para manejar tanto pickings como manufacturing orders"""
        # Manejar pickings (lógica original)
        if self.picking_ids:
            self.valuation_adjustment_lines.unlink()
            lines = self.get_valuation_lines(self.picking_ids.ids)
            self.valuation_adjustment_lines = lines
        
        # NUEVO: Manejar manufacturing orders
        if self.mrp_production_ids:
            # Si no hay picking_ids, limpiar las líneas existentes
            if not self.picking_ids:
                self.valuation_adjustment_lines.unlink()
            
            # Obtener líneas de valoración para manufacturing orders
            manufacturing_lines = self._get_manufacturing_valuation_lines()
            
            # Agregar las líneas de manufacturing
            if manufacturing_lines:
                if self.picking_ids:
                    # Si ya hay líneas de pickings, agregar las de manufacturing
                    self.valuation_adjustment_lines = self.valuation_adjustment_lines + manufacturing_lines
                else:
                    # Si no hay líneas de pickings, usar solo las de manufacturing
                    self.valuation_adjustment_lines = manufacturing_lines

    def _get_manufacturing_valuation_lines(self):
        """Crear líneas de ajuste de valoración para órdenes de fabricación"""
        lines = []
        
        for production in self.mrp_production_ids:
            # Solo procesar órdenes completadas
            if production.state != 'done':
                continue
            
            # Obtener los movimientos de productos terminados (finished products)
            finished_moves = production.move_finished_ids.filtered(
                lambda m: m.state == 'done' and m.product_id.cost_method in ('fifo', 'average')
            )
            
            for move in finished_moves:
                # Obtener las stock valuation layers del movimiento
                valuation_layers = move.stock_valuation_layer_ids.filtered(
                    lambda svl: svl.remaining_qty > 0
                )
                
                for svl in valuation_layers:
                    line_vals = self._prepare_manufacturing_valuation_adjustment_line(
                        production, move, svl
                    )
                    if line_vals:
                        lines.append((0, 0, line_vals))
        
        return lines

    def _prepare_manufacturing_valuation_adjustment_line(self, production, move, svl):
        """Preparar los valores para una línea de ajuste de valoración de manufacturing"""
        # Calcular el costo adicional total para esta línea
        total_cost = sum(line.price_unit for line in self.cost_lines)
        
        # Calcular la proporción que corresponde a este producto/cantidad
        if self._get_distribution_method() == 'by_quantity':
            # Distribución por cantidad
            total_qty = sum(
                layer.quantity for prod in self.mrp_production_ids
                for layer in prod.move_finished_ids.stock_valuation_layer_ids
                if layer.remaining_qty > 0
            )
            distribution_ratio = svl.quantity / total_qty if total_qty else 0
        elif self._get_distribution_method() == 'by_current_cost':
            # Distribución por costo actual
            total_value = sum(
                layer.value for prod in self.mrp_production_ids
                for layer in prod.move_finished_ids.stock_valuation_layer_ids
                if layer.remaining_qty > 0
            )
            distribution_ratio = abs(svl.value) / total_value if total_value else 0
        else:
            # Distribución igual (por defecto)
            total_moves = sum(
                len(prod.move_finished_ids.filtered(lambda m: m.state == 'done'))
                for prod in self.mrp_production_ids
            )
            distribution_ratio = 1.0 / total_moves if total_moves else 0
        
        additional_cost = total_cost * distribution_ratio
        
        return {
            'product_id': move.product_id.id,
            'quantity': svl.quantity,
            'unit_cost': svl.unit_cost,
            'value': abs(svl.value),  # Usar valor absoluto
            'additional_landed_cost': additional_cost,
            'weight': move.product_id.weight * svl.quantity,
            'volume': move.product_id.volume * svl.quantity,
        }

    def _get_distribution_method(self):
        """Obtener el método de distribución predominante de las líneas de costo"""
        if not self.cost_lines:
            return 'equal'
        
        # Usar el split_method de la primera línea como referencia
        return self.cost_lines[0].split_method

    def button_validate(self):
        """Override para mejorar la validación de costos en destino"""
        # Validaciones adicionales antes de procesar
        for record in self:
            if record.target_model == 'manufacturing' and record.mrp_production_ids:
                # Verificar que haya líneas de costo
                if not record.cost_lines:
                    raise UserError(_(
                        "No se puede validar un costo en destino sin líneas de costo."
                    ))
                
                # Verificar que las órdenes estén completadas
                incomplete_orders = record.mrp_production_ids.filtered(lambda p: p.state != 'done')
                if incomplete_orders:
                    raise UserError(_(
                        "No se puede validar un costo en destino con órdenes de fabricación incompletas: %s"
                    ) % ', '.join(incomplete_orders.mapped('name')))
                
                # Verificar que haya productos terminados con valoración correcta
                finished_products = record.mrp_production_ids.move_finished_ids.filtered(
                    lambda m: m.state == 'done' and m.product_id.cost_method in ('fifo', 'average')
                )
                if not finished_products:
                    raise UserError(_(
                        "No se encontraron productos terminados con método de costeo FIFO o Average. "
                        "Verifique la configuración de los productos."
                    ))
                
                # Verificar que haya stock valuation layers disponibles
                available_svls = finished_products.stock_valuation_layer_ids.filtered(
                    lambda svl: svl.remaining_qty > 0
                )
                if not available_svls:
                    record.message_post(
                        body=_("Advertencia: No se encontraron stock valuation layers con cantidad disponible. "
                              "Esto puede ocurrir si los productos ya fueron vendidos."),
                        message_type='comment'
                    )
                
                # Verificar que las líneas tengan costos asignados (solo advertencia)
                empty_cost_lines = record.cost_lines.filtered(lambda l: l.price_unit == 0.0)
                if empty_cost_lines:
                    empty_names = ', '.join(empty_cost_lines.mapped('name'))
                    record.message_post(
                        body=_("Advertencia: Las siguientes líneas tienen costo 0: %s") % empty_names,
                        message_type='comment'
                    )
        
        # Llamar al método padre para ejecutar la validación estándar
        return super().button_validate()

    def _create_accounting_entries(self, move):
        """Override para manejar entries contables de manufacturing"""
        # Si es manufacturing, usar lógica específica
        if self.target_model == 'manufacturing' and self.mrp_production_ids:
            return self._create_manufacturing_accounting_entries(move)
        
        # Si es picking, usar lógica estándar
        return super()._create_accounting_entries(move)

    def _create_manufacturing_accounting_entries(self, move):
        """Crear entries contables específicos para manufacturing"""
        # Por ahora, usar la lógica estándar pero con productos de manufacturing
        # En el futuro se puede personalizar para cuentas específicas de fabricación
        return super()._create_accounting_entries(move)


class StockLandedCostLines(models.Model):
    _inherit = 'stock.landed.cost.lines'
    
    is_manufacturing_cost = fields.Boolean(
        related='product_id.product_tmpl_id.is_landed_cost_manufacturing',
        string='Es costo de fabricación',
        readonly=True
    )
    
    @api.ondelete(at_uninstall=False)
    def _unlink_except_manufacturing_costs(self):
        """Eliminación libre de todas las líneas de landed cost"""
        # Eliminamos completamente la protección - el usuario puede eliminar cualquier línea
        pass
    
    def unlink(self):
        """Eliminar líneas proxy cuando se elimina la línea original"""
        # Buscar y eliminar líneas proxy relacionadas
        proxy_lines = self.env['mrp.production.cost.line'].search([
            ('landed_cost_line_id', 'in', self.ids)
        ])
        # Eliminar proxy lines sin triggear su unlink para evitar recursión
        if proxy_lines:
            self.env.cr.execute(
                "DELETE FROM mrp_production_cost_line WHERE id IN %s",
                (tuple(proxy_lines.ids),)
            )
        
        return super().unlink()
    
    @api.model_create_multi  
    def create(self, vals_list):
        """Override create para mejorar valores por defecto"""
        for vals in vals_list:
            # Si no hay split_method definido, usar 'equal' como defecto
            if 'split_method' not in vals:
                vals['split_method'] = 'equal'
            
            # Si hay producto pero no hay nombre, usar el nombre del producto
            if vals.get('product_id') and not vals.get('name'):
                product = self.env['product.product'].browse(vals['product_id'])
                if product:
                    vals['name'] = product.name
            
            # Si el producto tiene una cuenta de gastos configurada, usarla
            if vals.get('product_id') and not vals.get('account_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                if product and product.property_account_expense_id:
                    vals['account_id'] = product.property_account_expense_id.id
                elif product and product.categ_id.property_account_expense_categ_id:
                    vals['account_id'] = product.categ_id.property_account_expense_categ_id.id
        
        return super().create(vals_list)
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Llenar automáticamente campos cuando se selecciona un producto"""
        if self.product_id:
            # Establecer el nombre del producto si no está definido
            if not self.name:
                self.name = self.product_id.name
            
            # Establecer split_method por defecto si no está definido
            if not self.split_method:
                # Verificar si el producto tiene un método por defecto configurado
                if hasattr(self.product_id.product_tmpl_id, 'split_method_landed_cost'):
                    self.split_method = self.product_id.product_tmpl_id.split_method_landed_cost or 'equal'
                else:
                    self.split_method = 'equal'
            
            # Establecer la cuenta de gastos si no está definida
            if not self.account_id:
                if self.product_id.property_account_expense_id:
                    self.account_id = self.product_id.property_account_expense_id
                elif self.product_id.categ_id.property_account_expense_categ_id:
                    self.account_id = self.product_id.categ_id.property_account_expense_categ_id