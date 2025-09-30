/** @odoo-module **/

import { CharField } from "@web/views/fields/char/char_field";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";

export class SerialValidationField extends CharField {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        // Debounce validation to avoid too many server calls
        this.validateSerial = debounce(this._validateSerial.bind(this), 300);
        
        this.validationStatus = 'pending';
    }
    
    async onChange(ev) {
        await super.onChange(ev);
        
        const value = ev.target.value;
        if (value && this.props.record.data.picking_id && this.props.record.data.product_id) {
            await this.validateSerial(value);
        }
    }
    
    async _validateSerial(serialNumber) {
        if (!serialNumber) return;
        
        const pickingId = this.props.record.data.picking_id;
        const productId = this.props.record.data.product_id;
        const moveLineId = this.props.record.resId;
        
        try {
            // First, try to find existing lot
            const lots = await this.orm.searchRead(
                "stock.lot",
                [["name", "=", serialNumber], ["product_id", "=", productId]],
                ["id", "name", "product_id"]
            );
            
            let lotId = null;
            if (lots.length > 0) {
                lotId = lots[0].id;
            }
            
            if (lotId) {
                // Validate with existing lot
                const result = await this.orm.call(
                    "stock.picking",
                    "validate_serial_realtime",
                    [lotId, pickingId, productId, moveLineId]
                );
                
                this._handleValidationResult(result);
            } else {
                // For incoming operations, this might be a new serial number
                const picking = await this.orm.read("stock.picking", [pickingId], ["picking_type_id"]);
                if (picking[0].picking_type_id[1] === 'incoming') {
                    this.validationStatus = 'valid';
                    this._updateFieldAppearance();
                } else {
                    this.validationStatus = 'invalid';
                    this._updateFieldAppearance();
                    this.notification.add(
                        `Número de serie ${serialNumber} no encontrado`,
                        { type: "warning" }
                    );
                }
            }
        } catch (error) {
            console.error("Error validating serial number:", error);
            this.validationStatus = 'invalid';
            this._updateFieldAppearance();
        }
    }
    
    _handleValidationResult(result) {
        if (result.valid) {
            this.validationStatus = 'valid';
        } else {
            this.validationStatus = 'invalid';
            this.notification.add(result.message, {
                type: "warning",
                title: "Validación de número de serie"
            });
        }
        this._updateFieldAppearance();
    }
    
    _updateFieldAppearance() {
        const input = this.el.querySelector('input');
        if (!input) return;
        
        // Remove existing classes
        input.classList.remove('serial-valid', 'serial-invalid', 'serial-pending');
        
        // Add appropriate class
        switch (this.validationStatus) {
            case 'valid':
                input.classList.add('serial-valid');
                break;
            case 'invalid':
                input.classList.add('serial-invalid');
                break;
            case 'pending':
                input.classList.add('serial-pending');
                break;
        }
    }
}

SerialValidationField.template = "web.CharField";

registry.category("fields").add("serial_validation_field", SerialValidationField);