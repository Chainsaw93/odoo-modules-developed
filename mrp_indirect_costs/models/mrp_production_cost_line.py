from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class MrpProductionCostLine(models.Model):
    _name = 'mrp.production.cost.line'
    _description = 'Línea de costo indirecto de orden de fabricación'
    _order = 'sequence, id'
    
    # Campos principales
    production_id = fields.Many2one(
        'mrp.production',
        string='Orden de Fabricación',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    landed_cost_line_id = fields.Many2one(
        'stock.landed.cost.lines',
        string='Línea de Costo en Destino',
        required=False,  # No required en formulario, se valida después
        ondelete='cascade',
        index=True
    )
    
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Determina el orden de las líneas'
    )
    
    notes = fields.Text(
        string='Observaciones',
        help='Notas específicas para esta línea de costo en la orden de fabricación'
    )
    
    # Campos proxy que se sincronizan con la línea real
    product_id = fields.Many2one(
        'product.product',
        related='landed_cost_line_id.product_id',
        string='Producto',
        readonly=False,
        store=False  # Cambiar a False para evitar problemas de sincronización
    )
    
    name = fields.Char(
        related='landed_cost_line_id.name',
        string='Descripción',
        readonly=False,
        store=False  # Cambiar a False para evitar problemas de sincronización
    )
    
    price_unit = fields.Monetary(
        related='landed_cost_line_id.price_unit',
        string='Costo',
        readonly=False,
        store=False  # Cambiar a False para evitar problemas de sincronización
    )
    
    split_method = fields.Selection(
        related='landed_cost_line_id.split_method',
        string='Método de División',
        readonly=False,
        store=False  # Cambiar a False para evitar problemas de sincronización
    )
    
    is_manufacturing_cost = fields.Boolean(
        related='landed_cost_line_id.is_manufacturing_cost',
        string='Es costo de fabricación específico',
        readonly=True,
        help='Indica si este producto está específicamente marcado como costo de fabricación'
    )
    
    currency_id = fields.Many2one(
        related='landed_cost_line_id.currency_id',
        string='Moneda',
        readonly=True
    )
    
    account_id = fields.Many2one(
        related='landed_cost_line_id.account_id',
        string='Cuenta',
        readonly=False,
        store=False  # Cambiar a False para evitar problemas de sincronización
    )
    
    # Restricciones SQL
    _sql_constraints = [
        ('unique_landed_cost_line', 'unique(landed_cost_line_id)', 
         'Una línea de costo en destino solo puede estar asociada a una orden de fabricación.'),
        ('check_sequence_positive', 'check(sequence >= 0)', 
         'La secuencia debe ser un número positivo.')
    ]
    
    @api.constrains('landed_cost_line_id')
    def _check_landed_cost_line_required(self):
        """Validar que la línea de costo en destino existe"""
        for record in self:
            if not record.landed_cost_line_id:
                raise ValidationError(_(
                    "La línea de costo en destino es obligatoria. "
                    "Si ve este error, contacte al administrador del sistema."
                ))
    
    def _check_landed_cost_line_belongs_to_production(self):
        """Validar que la línea de costo pertenece al landed cost de la orden"""
        for record in self:
            # Solo validar si ambos campos están presentes
            if record.production_id and record.landed_cost_line_id and record.landed_cost_line_id.cost_id:
                if record.landed_cost_line_id.cost_id != record.production_id.landed_cost_id:
                    raise ValidationError(_(
                        "La línea de costo seleccionada no pertenece al costo en destino "
                        "de esta orden de fabricación."
                    ))
    
    @api.constrains('product_id')
    def _check_product_is_landed_cost(self):
        """Validar que el producto es apto para costos en destino"""
        for record in self:
            # Solo validar si el producto está presente y tiene template
            if record.product_id and record.product_id.product_tmpl_id:
                template = record.product_id.product_tmpl_id
                if not (template.landed_cost_ok or template.is_landed_cost_manufacturing):
                    raise ValidationError(_(
                        "El producto '%s' no está configurado como costo en destino."
                    ) % record.product_id.display_name)
    
    @api.ondelete(at_uninstall=False)
    def _unlink_check_manufacturing_costs(self):
        """Eliminación libre de todas las líneas de costo"""
        # Eliminamos completamente la protección - el usuario puede eliminar cualquier línea
        pass
    
    def unlink(self):
        """Eliminar líneas del landed cost cuando se elimina el proxy"""
        landed_cost_lines = self.mapped('landed_cost_line_id')
        result = super().unlink()
        # Eliminar las líneas del landed cost después de eliminar el proxy
        landed_cost_lines.unlink()
        return result
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create para crear línea landed cost automáticamente"""
        for vals in vals_list:
            # Si no hay landed_cost_line_id, crear uno automáticamente
            if not vals.get('landed_cost_line_id'):
                # Obtener production_id de vals o del contexto
                production_id = vals.get('production_id') or self.env.context.get('default_production_id')
                
                if not production_id:
                    raise UserError(_("Falta el ID de la orden de fabricación."))
                
                production = self.env['mrp.production'].browse(production_id)
                if not production.exists():
                    raise UserError(_("No se encontró la orden de fabricación."))
                
                # Asegurar que production_id esté en vals
                vals['production_id'] = production_id
                
                if not production.landed_cost_id:
                    production._create_landed_cost()
                
                if not production.landed_cost_id:
                    raise UserError(_("No se pudo crear el costo en destino."))
                
                # Verificar campos requeridos
                product_id = vals.get('product_id')
                if not product_id:
                    raise UserError(_("Debe seleccionar un producto."))
                
                # Obtener el producto para usar su nombre como descripción
                product = self.env['product.product'].browse(product_id)
                name = vals.get('name')
                if not name and product:
                    name = product.name
                    vals['name'] = name
                
                if not name:
                    vals['name'] = 'Nuevo costo'
                    name = 'Nuevo costo'
                
                # Crear la línea en landed cost con valores mejorados
                landed_cost_line_vals = {
                    'cost_id': production.landed_cost_id.id,
                    'product_id': product_id,
                    'name': name,
                    'price_unit': vals.get('price_unit', 0.0),
                    'split_method': vals.get('split_method', 'equal'),  # Por defecto = igual
                }
                
                # Si el producto tiene una cuenta de gastos configurada, usarla
                if product and product.property_account_expense_id:
                    landed_cost_line_vals['account_id'] = product.property_account_expense_id.id
                elif product and product.categ_id.property_account_expense_categ_id:
                    landed_cost_line_vals['account_id'] = product.categ_id.property_account_expense_categ_id.id
                
                landed_cost_line = self.env['stock.landed.cost.lines'].create(landed_cost_line_vals)
                vals['landed_cost_line_id'] = landed_cost_line.id
        
        records = super().create(vals_list)
        
        return records
    
    def write(self, vals):
        """Override write para sincronizar cambios con landed cost line"""
        result = super().write(vals)
        
        # Revalidar después de modificar
        if 'production_id' in vals or 'landed_cost_line_id' in vals:
            self._check_landed_cost_line_belongs_to_production()
            
        return result
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Llenar automáticamente el nombre cuando se selecciona un producto"""
        if self.product_id:
            self.name = self.product_id.name
            # Si no hay split_method definido, establecer 'equal' por defecto
            if not self.split_method:
                self.split_method = 'equal'
    
    @api.model
    def create_proxy_lines_for_production(self, production):
        """Crear líneas proxy para una orden de fabricación específica"""
        if not production.landed_cost_id:
            return self.env['mrp.production.cost.line']
        
        # Eliminar líneas proxy existentes para evitar duplicados
        existing_proxies = self.search([('production_id', '=', production.id)])
        existing_proxies.unlink()
        
        # Crear nuevas líneas proxy solo para las líneas del landed cost de esta orden
        proxy_lines = self.env['mrp.production.cost.line']
        sequence = 10
        
        for cost_line in production.landed_cost_id.cost_lines:
            proxy_line = self.create({
                'production_id': production.id,
                'landed_cost_line_id': cost_line.id,
                'sequence': sequence,
            })
            proxy_lines |= proxy_line
            sequence += 10
            
        return proxy_lines
    
    def action_view_landed_cost_line(self):
        """Acción para ver la línea de costo en destino original"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Línea de Costo en Destino'),
            'res_model': 'stock.landed.cost.lines',
            'res_id': self.landed_cost_line_id.id,
            'view_mode': 'form',
            'target': 'new',
        }