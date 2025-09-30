odoo.define('stock_picking_sale_validation.barcode_validation', function (require) {
"use strict";

var core = require('web.core');
var Dialog = require('web.Dialog');
var StockBarcodePickingClientAction = require('stock_barcode.picking_client_action');
var _t = core._t;

// Extender la acción de cliente de códigos de barras
StockBarcodePickingClientAction.include({

    init: function () {
        this._super.apply(this, arguments);
        this.allowed_products = [];
        this.validation_active = false;
        this.sale_order_name = '';
    },

    start: function () {
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            // Cargar información de productos permitidos
            self._loadPickingValidationInfo();

            // ➕ NUEVO: Mostrar alerta si tipo = 'outgoing' y tiene origin
            const picking = self.model && self.model.picking;
            if (picking && picking.picking_type_code === 'outgoing' && picking.origin) {
                const $alert = $(`
                    <div class="alert alert-warning o_barcode_notice mb-2">
                        <i class="fa fa-info-circle"></i>
                        <strong>Restricción:</strong> Solo productos del pedido ${picking.origin}
                    </div>
                `);
                self.$('.o_barcode_generic_view').prepend($alert);
            }
        });
    },

    _loadPickingValidationInfo: function () {
        var self = this;
        if (this.actionParams && this.actionParams.pickingId) {
            return this._rpc({
                route: '/stock_barcode/get_picking_info',
                params: {
                    picking_id: this.actionParams.pickingId
                }
            }).then(function (result) {
                if (result.success) {
                    self.validation_active = result.validation_active;
                    self.sale_order_name = result.sale_order_name;
                    
                    if (self.validation_active) {
                        self._loadAllowedProducts();
                        self._showValidationWarning();
                    }
                }
            });
        }
    },

    _loadAllowedProducts: function () {
        var self = this;
        return this._rpc({
            route: '/stock_barcode/get_allowed_products',
            params: {
                picking_id: this.actionParams.pickingId
            }
        }).then(function (result) {
            if (result.success && !result.all_products_allowed) {
                self.allowed_products = result.products || [];
            }
        });
    },

    _showValidationWarning: function () {
        if (this.validation_active && this.sale_order_name) {
            this.$('.o_barcode_generic_view').prepend(
                $('<div class="alert alert-warning" role="alert">')
                    .append('<i class="fa fa-exclamation-triangle"></i> ')
                    .append('<strong>Restricción Activa:</strong> ')
                    .append('Solo se pueden agregar productos del pedido de venta ')
                    .append('<strong>' + this.sale_order_name + '</strong>')
            );
        }
    },

    _onBarcodeScanned: function (barcode) {
        var self = this;
        
        if (this.validation_active) {
            // Validar el código de barras antes de procesarlo
            return this._rpc({
                route: '/stock_barcode/scan_product',
                params: {
                    picking_id: this.actionParams.pickingId,
                    barcode: barcode
                }
            }).then(function (result) {
                if (result.success) {
                    // Si es válido, procesar normalmente
                    self._showNotification('success', _t('Producto válido: ') + result.product_name);
                    return self._super(barcode);
                } else {
                    // Si no es válido, mostrar error
                    self._showNotification('danger', result.message);
                    return Promise.reject(result.message);
                }
            }).catch(function (error) {
                self._showNotification('danger', _t('Error validando código de barras: ') + error);
                return Promise.reject(error);
            });
        } else {
            // Si no hay validación activa, procesar normalmente
            return this._super(barcode);
        }
    },

    _showNotification: function (type, message) {
        this.displayNotification({
            type: type,
            message: message,
            sticky: false
        });
    },

    _onAddProduct: function (ev) {
        var self = this;
        
        if (this.validation_active) {
            // Mostrar solo productos permitidos en el selector
            this._showProductSelector();
        } else {
            return this._super.apply(this, arguments);
        }
    },

    _showProductSelector: function () {
        var self = this;
        
        if (this.allowed_products.length === 0) {
            this._showNotification('warning', _t('No hay productos disponibles para este pedido'));
            return;
        }

        var products_html = this.allowed_products.map(function (product) {
            return '<tr data-product-id="' + product.id + '">' +
                '<td>' + product.name + '</td>' +
                '<td>' + (product.default_code || '') + '</td>' +
                '<td>' + (product.barcode || '') + '</td>' +
                '<td>' + product.qty_remaining + ' ' + product.uom_name + '</td>' +
                '<td><button class="btn btn-primary btn-sm select-product">Seleccionar</button></td>' +
                '</tr>';
        }).join('');

        var dialog_content = 
            '<div class="container-fluid">' +
                '<h5>Productos disponibles del pedido: ' + this.sale_order_name + '</h5>' +
                '<table class="table table-striped">' +
                    '<thead>' +
                        '<tr>' +
                            '<th>Producto</th>' +
                            '<th>Código</th>' +
                            '<th>Código de barras</th>' +
                            '<th>Cantidad pendiente</th>' +
                            '<th>Acción</th>' +
                        '</tr>' +
                    '</thead>' +
                    '<tbody>' + products_html + '</tbody>' +
                '</table>' +
            '</div>';

        var dialog = new Dialog(this, {
            title: _t('Seleccionar Producto'),
            size: 'large',
            $content: $(dialog_content),
            buttons: [{
                text: _t('Cerrar'),
                classes: 'btn-secondary',
                close: true
            }]
        });

        dialog.opened().then(function () {
            dialog.$('.select-product').on('click', function (ev) {
                var product_id = parseInt($(ev.target).closest('tr').data('product-id'));
                var product = self.allowed_products.find(p => p.id === product_id);
                
                if (product) {
                    // Simular escaneo del código de barras del producto
                    var barcode = product.barcode || product.default_code || product.id.toString();
                    self._onBarcodeScanned(barcode);
                }
                
                dialog.close();
            });
        });

        dialog.open();
    },

    _showAllowedProductsList: function () {
        var self = this;
        
        return this._rpc({
            route: '/stock_barcode/get_allowed_products',
            params: {
                picking_id: this.actionParams.pickingId
            }
        }).then(function (result) {
            if (result.success) {
                if (result.all_products_allowed) {
                    self._showNotification('info', _t('Todos los productos están permitidos'));
                } else {
                    var products_list = result.products.map(function (product) {
                        return '• ' + product.name + 
                               (product.default_code ? ' [' + product.default_code + ']' : '') +
                               ' - Pendiente: ' + product.qty_remaining + ' ' + product.uom_name;
                    }).join('\n');
                    
                    var dialog = new Dialog(self, {
                        title: _t('Productos Permitidos - ') + result.sale_order_name,
                        size: 'medium',
                        $content: $('<div>').html('<pre>' + products_list + '</pre>'),
                        buttons: [{
                            text: _t('Cerrar'),
                            classes: 'btn-secondary',
                            close: true
                        }]
                    });
                    
                    dialog.open();
                }
            } else {
                self._showNotification('danger', result.message);
            }
        });
    },

    // Agregar botón para mostrar productos permitidos
    _renderButtons: function () {
        var self = this;
        this._super.apply(this, arguments);
        
        if (this.validation_active) {
            var $show_products_btn = $('<button type="button" class="btn btn-info btn-sm ml-2">')
                .text(_t('Ver Productos Permitidos'))
                .on('click', function () {
                    self._showAllowedProductsList();
                });
            
            this.$buttons.append($show_products_btn);
        }
    },

    // Override para manejar errores de validación
    _onBarcodeErrorAction: function (error) {
        if (error && error.includes('pedido de venta')) {
            this._showNotification('danger', error);
        } else {
            this._super.apply(this, arguments);
        }
    }

});

// Extender también la vista de lista de productos para aplicar filtros
var FieldMany2One = require('web.relational_fields').FieldMany2One;

FieldMany2One.include({
    
    _search: function (search_val) {
        var self = this;
        
        // Aplicar filtros especiales para productos en pickings
        if (this.name === 'product_id' && this.model === 'stock.move') {
            var context = this.record.getContext();
            if (context.picking_id) {
                // Agregar filtro de productos permitidos
                return this._rpc({
                    route: '/stock_barcode/get_allowed_products',
                    params: {
                        picking_id: context.picking_id
                    }
                }).then(function (result) {
                    if (result.success && !result.all_products_allowed) {
                        var allowed_ids = result.products.map(p => p.id);
                        var domain = [['id', 'in', allowed_ids]];
                        
                        if (search_val) {
                            domain.push('|', ['name', 'ilike', search_val], ['default_code', 'ilike', search_val]);
                        }
                        
                        return self._rpc({
                            model: 'product.product',
                            method: 'name_search',
                            args: [search_val || ''],
                            kwargs: {
                                args: domain,
                                limit: self.limit,
                                context: self.getSearchContext()
                            }
                        });
                    } else {
                        return self._super(search_val);
                    }
                });
            }
        }
        
        return this._super.apply(this, arguments);
    }
});

});