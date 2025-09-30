/** @odoo-module **/

import { BarcodePickingClientAction } from "@stock_barcode/client_action/picking_client_action";
import { patch } from "@web/core/utils/patch";

patch(BarcodePickingClientAction.prototype, {
    
    async _processBarcode(barcode) {
        // Check if we're dealing with serial number tracking
        const hasSerialProducts = this.state.lines.some(line => 
            line.product_tracking === 'serial'
        );
        
        if (hasSerialProducts && this._isSerialNumber(barcode)) {
            return await this._processSerialNumber(barcode);
        }
        
        return super._processBarcode(barcode);
    },
    
    _isSerialNumber(barcode) {
        // Heuristic to determine if barcode is a serial number
        // This can be customized based on your serial number format
        return barcode.length >= 6 && /^[A-Z0-9\-_]+$/i.test(barcode);
    },
    
    async _processSerialNumber(serialNumber) {
        try {
            const result = await this.orm.call(
                "stock.picking",
                "barcode_validate_serial",
                [serialNumber, this.state.id]
            );
            
            if (!result.validation.valid) {
                this.notification.add(result.validation.message, {
                    type: "warning",
                    title: "Error de validación"
                });
                return;
            }
            
            // Process successful serial number scan
            await this._addSerialToLine(result.lot_id, result.product_id);
            
            this.notification.add(
                `Número de serie ${serialNumber} agregado correctamente`, {
                type: "success"
            });
            
        } catch (error) {
            console.error("Error processing serial number:", error);
            this.notification.add(
                "Error procesando número de serie", {
                type: "danger"
            });
        }
    },
    
    async _addSerialToLine(lotId, productId) {
        // Find appropriate line for this product
        const targetLine = this.state.lines.find(line => 
            line.product_id === productId && !line.lot_id
        );
        
        if (targetLine) {
            // Update existing line
            await this.orm.write("stock.move.line", [targetLine.id], {
                lot_id: lotId,
                quantity: 1.0
            });
        } else {
            // Create new line if needed
            const moves = await this.orm.searchRead(
                "stock.move",
                [["picking_id", "=", this.state.id], ["product_id", "=", productId]],
                ["id"]
            );
            
            if (moves.length > 0) {
                await this.orm.create("stock.move.line", {
                    move_id: moves[0].id,
                    picking_id: this.state.id,
                    product_id: productId,
                    lot_id: lotId,
                    quantity: 1.0,
                    location_id: this.state.location_id,
                    location_dest_id: this.state.location_dest_id
                });
            }
        }
        
        // Refresh the view
        await this._refreshState();
    }
});