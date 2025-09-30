from odoo import models, fields, api
from odoo.exceptions import UserError

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    qqwewe = fields.Char(string="Mi Nuevo Campo")
   
    def write(self, vals):
        """Controlar escritura en líneas de factura según permisos y condiciones - SOLO FACTURAS DE VENTA"""
        # Verificar múltiples contextos que indican creación desde orden de venta
        creating_from_sale = (
            self.env.context.get('creating_from_sale_order', False) or
            self.env.context.get('skip_draft_invoice_validation', False) or
            self.env.context.get('active_model') == 'sale.order'
        )
        
        # Verificar si el usuario puede modificar facturas borrador
        can_modify_draft = self.env.user.has_group('bloqueo_factura_ventas_borrador.group_modify_draft_invoice')
        
        for line in self:
            # SOLO aplicar a líneas de facturas de venta (out_invoice)
            # Para facturas de proveedor, nota de crédito, etc., no aplicar ninguna restricción
            if line.move_id.move_type != 'out_invoice':
                continue
                
            # 1. RESTRICCIONES PARA FACTURAS DE VENTA EN BORRADOR
            # Solo aplicar restricciones si NO estamos creando desde orden de venta
            # Y el usuario NO tiene permisos para modificar facturas borrador
            if (line.move_id.state == 'draft' and 
                not creating_from_sale and
                not can_modify_draft):  # Solo aplicar si NO tiene permisos
                
                restricted_fields = ['price_unit', 'quantity', 'discount']
                
                for field in restricted_fields:
                    if field in vals:
                        raise UserError(f"No tiene permisos para modificar {field} en líneas de factura de venta borrador.")
           
            # 2. RESTRICCIONES PARA FACTURAS DE VENTA PROVENIENTES DE PEDIDOS DE VENTA
            # Solo aplicar si NO estamos creando desde orden de venta
            # Y el usuario NO tiene permisos
            if (line.move_id.invoice_origin and 
                not creating_from_sale and
                line.move_id.state in ['draft', 'posted'] and
                not can_modify_draft):  # Solo aplicar si NO tiene permisos
                
                # Campos críticos que no se pueden modificar
                restricted_fields = ['price_unit', 'quantity', 'discount', 'product_id', 'name', 'account_id', 'tax_ids']
               
                for field in restricted_fields:
                    if field in vals:
                        raise UserError(f"No se puede modificar {field} en facturas de venta provenientes de pedidos de venta.")
       
        return super().write(vals)
   
    def unlink(self):
        """Controlar eliminación de líneas en facturas con restricciones - SOLO FACTURAS DE VENTA"""
        # Verificar múltiples contextos que indican creación desde orden de venta
        creating_from_sale = (
            self.env.context.get('creating_from_sale_order', False) or
            self.env.context.get('skip_draft_invoice_validation', False) or
            self.env.context.get('active_model') == 'sale.order'
        )
        
        # Verificar si el usuario puede modificar facturas borrador
        can_modify_draft = self.env.user.has_group('bloqueo_factura_ventas_borrador.group_modify_draft_invoice')
        
        for line in self:
            # SOLO aplicar a líneas de facturas de venta (out_invoice)
            # Para facturas de proveedor, nota de crédito, etc., no aplicar ninguna restricción
            if line.move_id.move_type != 'out_invoice':
                continue
                
            # 1. RESTRICCIONES PARA FACTURAS DE VENTA EN BORRADOR
            # Solo aplicar restricciones si NO estamos creando desde orden de venta
            # Y el usuario NO tiene permisos para modificar facturas borrador
            if (line.move_id.state == 'draft' and 
                not creating_from_sale and
                not can_modify_draft):  # Solo aplicar si NO tiene permisos
                
                raise UserError("No tiene permisos para eliminar líneas en facturas de venta borrador.")
           
            # 2. RESTRICCIONES PARA FACTURAS DE VENTA PROVENIENTES DE PEDIDOS DE VENTA
            # Solo aplicar si NO estamos creando desde orden de venta
            # Y el usuario NO tiene permisos
            if (line.move_id.invoice_origin and 
                not creating_from_sale and
                line.move_id.state in ['draft', 'posted'] and
                not can_modify_draft):  # Solo aplicar si NO tiene permisos
                
                raise UserError("No se pueden eliminar líneas de facturas de venta provenientes de pedidos de venta.")
       
        return super().unlink()
   
    @api.model
    def create(self, vals_list):
        """Controlar creación de líneas en facturas con restricciones - SOLO FACTURAS DE VENTA"""
        # Verificar múltiples contextos que indican creación desde orden de venta
        creating_from_sale = (
            self.env.context.get('creating_from_sale_order', False) or
            self.env.context.get('skip_draft_invoice_validation', False) or
            self.env.context.get('active_model') == 'sale.order'
        )
        
        # Verificar si el usuario puede modificar facturas borrador
        can_modify_draft = self.env.user.has_group('bloqueo_factura_ventas_borrador.group_modify_draft_invoice')
        
        if not isinstance(vals_list, list):
            vals_list = [vals_list]
       
        for vals in vals_list:
            if 'move_id' in vals:
                move = self.env['account.move'].browse(vals['move_id'])
                
                # SOLO aplicar a facturas de venta (out_invoice)
                # Para facturas de proveedor, nota de crédito, etc., no aplicar ninguna restricción
                if move.move_type != 'out_invoice':
                    continue
                    
                # 1. RESTRICCIONES PARA FACTURAS DE VENTA EN BORRADOR
                # Solo aplicar si NO estamos creando desde orden de venta
                # Y el usuario NO tiene permisos para modificar facturas borrador
                if (move.state == 'draft' and 
                    not creating_from_sale and
                    not can_modify_draft):  # Solo aplicar si NO tiene permisos
                    
                    raise UserError("No tiene permisos para agregar líneas en facturas de venta borrador.")
                
                # 2. RESTRICCIONES PARA FACTURAS DE VENTA PROVENIENTES DE PEDIDOS DE VENTA
                # Solo aplicar si NO estamos creando desde orden de venta
                # Y el usuario NO tiene permisos
                if (move.invoice_origin and 
                    not creating_from_sale and
                    move.state in ['draft', 'posted'] and
                    not can_modify_draft):  # Solo aplicar si NO tiene permisos
                    
                    raise UserError("No se pueden agregar líneas a facturas de venta provenientes de pedidos de venta.")
       
        return super().create(vals_list)