from odoo import models, fields, api
from collections import defaultdict
import base64
import io
try:
    import barcode
    from barcode.writer import ImageWriter
    HAS_BARCODE = True
except ImportError:
    HAS_BARCODE = False


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _get_grouped_moves_for_conduce(self):
        """
        Groups stock moves by product for the Conduce report.
        For products with serial/lot tracking, combines all moves of the same product
        into a single line with aggregated serial numbers and lots.
        """
        grouped_moves = defaultdict(lambda: {
            'product': None,
            'quantity': 0,
            'serials': [],
            'lots': [],
            'line_notes': []
        })
        
        # Filter moves that are done or have quantity
        moves_to_process = self.move_ids.filtered(lambda m: m.state == 'done' or (hasattr(m, 'quantity') and m.quantity > 0) or (hasattr(m, 'product_uom_qty') and m.product_uom_qty > 0))
        
        for move in moves_to_process:
            # Use product_id as key for grouping
            key = move.product_id.id
            
            if not grouped_moves[key]['product']:
                grouped_moves[key]['product'] = move.product_id
            
            # Add quantity - handle different quantity field names
            quantity = 0
            if hasattr(move, 'quantity') and move.quantity:
                quantity = move.quantity
            elif hasattr(move, 'product_uom_qty') and move.product_uom_qty:
                quantity = move.product_uom_qty
            elif hasattr(move, 'quantity_done') and move.quantity_done:
                quantity = move.quantity_done
            
            grouped_moves[key]['quantity'] += quantity
            
            # Collect serial numbers and lots from move lines
            if hasattr(move, 'move_line_ids'):
                for move_line in move.move_line_ids:
                    # Handle lot_id (which can be either lot or serial in newer versions)
                    if hasattr(move_line, 'lot_id') and move_line.lot_id:
                        lot_name = move_line.lot_id.name
                        
                        # Determine if this is a serial or lot based on product tracking
                        is_serial = False
                        if hasattr(move.product_id, 'tracking'):
                            is_serial = move.product_id.tracking == 'serial'
                        
                        # Alternative check: if qty_done is 1, it's likely a serial
                        if not is_serial and hasattr(move_line, 'qty_done'):
                            is_serial = move_line.qty_done == 1.0
                        elif not is_serial and hasattr(move_line, 'quantity'):
                            is_serial = move_line.quantity == 1.0
                        
                        if is_serial:
                            if lot_name not in grouped_moves[key]['serials']:
                                grouped_moves[key]['serials'].append(lot_name)
                        else:
                            if lot_name not in grouped_moves[key]['lots']:
                                grouped_moves[key]['lots'].append(lot_name)
                    
                    # Legacy support for separate serial_id field (older versions)
                    elif hasattr(move_line, 'serial_id') and move_line.serial_id:
                        serial_name = move_line.serial_id.name
                        if serial_name not in grouped_moves[key]['serials']:
                            grouped_moves[key]['serials'].append(serial_name)
            
            # Collect line notes - only check line_note field
            if hasattr(move, 'line_note') and move.line_note:
                note = move.line_note.strip()
                # Add note if it exists and is not already in the list
                if note and note not in grouped_moves[key]['line_notes']:
                    grouped_moves[key]['line_notes'].append(note)
        
        # Convert to list and sort serials/lots, join notes
        result = []
        for data in grouped_moves.values():
            if data['serials']:
                data['serials'].sort()
            if data['lots']:
                data['lots'].sort()
            
            # Join all notes with newlines for display
            data['line_notes'] = '\n'.join(data['line_notes']) if data['line_notes'] else ''
            
            result.append(data)
        
        # Sort by product name
        result.sort(key=lambda x: x['product'].name if x['product'] else '')
        return result

    def get_barcode_image(self):
        """
        Generate barcode image for the conduce reference
        """
        if not self.name:
            return False
            
        try:
            # Try using Odoo's built-in barcode generation
            from odoo.addons.web.controllers.main import ReportController
            return f"/report/barcode/?type=Code128&value={self.name}&width=200&height=50"
        except:
            # Fallback: generate barcode using python-barcode if available
            if HAS_BARCODE:
                try:
                    code128 = barcode.get_barcode_class('code128')
                    barcode_instance = code128(self.name, writer=ImageWriter())
                    buffer = io.BytesIO()
                    barcode_instance.write(buffer)
                    barcode_image = base64.b64encode(buffer.getvalue()).decode()
                    return f"data:image/png;base64,{barcode_image}"
                except:
                    return False
            return False

    def get_barcode_url(self):
        """
        Get barcode URL for template
        """
        if not self.name:
            return ""
        return f"/report/barcode/?type=Code128&value={self.name}&width=200&height=50"