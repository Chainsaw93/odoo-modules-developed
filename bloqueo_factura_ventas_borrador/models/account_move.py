from odoo import models, fields, api
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    can_modify_draft_invoice = fields.Boolean(
        string="Can Modify Draft Invoice",
        compute="_compute_can_modify_draft_invoice",
        help="Campo técnico para controlar permisos en vistas de facturas de venta"
    )
    
    @api.depends_context('uid')
    def _compute_can_modify_draft_invoice(self):
        """Calcular si el usuario actual puede modificar facturas borrador - SOLO PARA FACTURAS DE VENTA"""
        for move in self:
            # Solo calcular para facturas de venta, para las demás siempre True (sin restricciones)
            if move.move_type == 'out_invoice':
                move.can_modify_draft_invoice = self.env.user.has_group('bloqueo_factura_ventas_borrador.group_modify_draft_invoice')
            else:
                move.can_modify_draft_invoice = True
   
    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """Sobrescribir para agregar contexto que controle la readonly de campos"""
        result = super().get_view(view_id, view_type, **options)
       
        if view_type == 'form':
            # Agregar contexto para controlar readonly
            context = self.env.context.copy()
           
            # Verificar si el usuario actual puede modificar facturas borrador
            can_modify_draft = self.env.user.has_group('bloqueo_factura_ventas_borrador.group_modify_draft_invoice')
           
            if not can_modify_draft:
                context['readonly_invoice_fields'] = True
                context['readonly_journal_field'] = True
           
            result['context'] = context
           
        return result
   
    def write(self, vals):
        """Controlar escritura en facturas según permisos y estado - SOLO FACTURAS DE VENTA"""
        # Verificar múltiples contextos que indican creación desde orden de venta
        creating_from_sale = (
            self.env.context.get('creating_from_sale_order', False) or
            self.env.context.get('active_model') == 'sale.order' or
            self.env.context.get('default_move_type') == 'out_invoice'
        )
        
        # Verificar si el usuario puede modificar facturas borrador
        can_modify_draft = self.env.user.has_group('bloqueo_factura_ventas_borrador.group_modify_draft_invoice')
        
        for move in self:
            # SOLO aplicar restricciones a facturas de venta (out_invoice)
            # Para facturas de proveedor, nota de crédito, etc., no aplicar ninguna restricción
            if move.move_type != 'out_invoice':
                continue
                
            # 1. RESTRICCIONES PARA FACTURAS DE VENTA EN BORRADOR
            # Solo aplicar restricciones si NO estamos creando desde orden de venta
            # Y el usuario NO tiene permisos para modificar facturas borrador
            if (move.state == 'draft' and 
                not creating_from_sale and
                not can_modify_draft):  # Solo aplicar si NO tiene permisos
                
                restricted_fields = ['journal_id']
                line_restricted_fields = ['price_unit', 'quantity', 'discount']
                
                # Verificar campos restringidos en el movimiento
                for field in restricted_fields:
                    if field in vals:
                        raise UserError(f"No tiene permisos para modificar {field} en facturas de venta borrador.")
               
                # Verificar campos restringidos en las líneas
                if 'invoice_line_ids' in vals:
                    for line_vals in vals['invoice_line_ids']:
                        if isinstance(line_vals, (list, tuple)) and len(line_vals) >= 3:
                            line_data = line_vals[2] if line_vals[0] in [0, 1] else {}
                            for field in line_restricted_fields:
                                if field in line_data:
                                    raise UserError(f"No tiene permisos para modificar {field} en líneas de factura de venta borrador.")
           
            # 2. RESTRICCIONES PARA FACTURAS DE VENTA PROVENIENTES DE PEDIDOS DE VENTA
            # Solo aplicar si NO estamos creando desde orden de venta, la factura ya existe
            # Y el usuario NO tiene permisos
            if (move.invoice_origin and 
                not creating_from_sale and 
                move.id and  # La factura ya debe existir
                move.state in ['draft', 'posted'] and
                not can_modify_draft):  # Solo aplicar si NO tiene permisos
                
                # Campos restringidos en líneas de factura
                line_restricted_fields = ['price_unit', 'quantity', 'discount', 'product_id', 'name', 'account_id', 'tax_ids']
               
                # Verificar modificaciones en líneas
                if 'invoice_line_ids' in vals:
                    for line_vals in vals['invoice_line_ids']:
                        if isinstance(line_vals, (list, tuple)) and len(line_vals) >= 1:
                            operation = line_vals[0]
                            
                            # Operación 0: crear nueva línea - NO PERMITIDO
                            if operation == 0:
                                raise UserError("No se pueden agregar líneas a facturas de venta provenientes de pedidos de venta.")
                            
                            # Operación 1: actualizar línea existente - VERIFICAR CAMPOS
                            elif operation == 1 and len(line_vals) >= 3:
                                line_data = line_vals[2]
                                for field in line_restricted_fields:
                                    if field in line_data:
                                        raise UserError(f"No se puede modificar {field} en facturas de venta provenientes de pedidos de venta.")
                            
                            # Operación 2: eliminar línea - NO PERMITIDO
                            elif operation == 2:
                                raise UserError("No se pueden eliminar líneas de facturas de venta provenientes de pedidos de venta.")
                
                # También verificar otros campos del encabezado que podrían ser problemáticos
                restricted_header_fields = ['partner_id', 'currency_id', 'invoice_date', 'payment_term_id']
                for field in restricted_header_fields:
                    if field in vals:
                        raise UserError(f"No se puede modificar {field} en facturas de venta provenientes de pedidos de venta.")
       
        return super().write(vals)
    
    @api.model
    def create(self, vals_list):
        """Sobrescribir create para mantener el contexto durante la creación"""
        if not isinstance(vals_list, list):
            vals_list = [vals_list]
        
        # Propagar el contexto de creación desde orden de venta
        creating_from_sale = (
            self.env.context.get('creating_from_sale_order', False) or
            self.env.context.get('active_model') == 'sale.order' or
            self.env.context.get('default_move_type') == 'out_invoice'
        )
        
        if creating_from_sale:
            # Asegurar que el contexto se mantenga durante toda la creación
            return super(AccountMove, self.with_context(
                creating_from_sale_order=True,
                skip_draft_invoice_validation=True
            )).create(vals_list)
        
        return super().create(vals_list)