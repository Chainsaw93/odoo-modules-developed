from odoo import models, fields

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def get_cost_analysis(self):
        # 1. Obtener el análisis de costo original
        res = super().get_cost_analysis()
        
        # 2. Encontrar los costos indirectos asociados a esta OF
        landed_costs_data = []
        total_landed_cost = 0.0
        
        # Buscar en los movimientos de producto terminado
        for move in self.move_finished_ids.filtered(lambda m: m.state == 'done'):
            # Encontrar las líneas de ajuste de valoración para cada movimiento
            valuation_lines = self.env['stock.valuation.adjustment.lines'].search([
                ('cost_line_id.stock_move_id', '=', move.id)
            ])
            for line in valuation_lines:
                total_landed_cost += line.additional_landed_cost
                landed_costs_data.append({
                    'name': line.cost_id.name,
                    'quantity': self.product_qty,
                    'unit_price': line.additional_landed_cost / self.product_qty if self.product_qty else 0,
                    'cost': line.additional_landed_cost,
                })

        # 3. Inyectar los nuevos datos en el resultado
        if landed_costs_data:
            # Añadir el agrupador y el total a la respuesta
            res.append({
                'name': 'Costos indirectos',
                'landed_costs': landed_costs_data,
                'total_landed_cost': total_landed_cost
            })
            
            # 4. Actualizar el costo real del producto principal
            for data in res:
                if data.get('product_cost'):
                    # El costo real es la suma del costo de componentes y operaciones
                    # Le añadimos el nuevo costo indirecto
                    current_real_cost = data['product_cost'][0].get('real_cost', 0.0)
                    data['product_cost'][0]['real_cost'] = current_real_cost + total_landed_cost
                    break

        return res