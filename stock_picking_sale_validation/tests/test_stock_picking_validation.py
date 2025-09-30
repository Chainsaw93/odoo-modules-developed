# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo import fields

class TestStockPickingValidation(TransactionCase):
    """
    Tests para validar la funcionalidad del módulo de validación de stock picking
    """

    def setUp(self):
        super().setUp()
        
        # Crear productos de prueba
        self.product1 = self.env['product.product'].create({
            'name': 'Producto Test 1',
            'default_code': 'PROD001',
            'barcode': '1234567890123',
            'type': 'product',
        })
        
        self.product2 = self.env['product.product'].create({
            'name': 'Producto Test 2', 
            'default_code': 'PROD002',
            'barcode': '1234567890124',
            'type': 'product',
        })
        
        self.product3 = self.env['product.product'].create({
            'name': 'Producto Test 3',
            'default_code': 'PROD003', 
            'barcode': '1234567890125',
            'type': 'product',
        })
        
        # Crear UOM de prueba
        self.uom_caja = self.env['uom.uom'].create({
            'name': 'Caja',
            'category_id': self.env.ref('uom.product_uom_categ_unit').id,
            'factor': 1.0,
            'uom_type': 'reference',
        })
        
        # Crear cliente
        self.customer = self.env['res.partner'].create({
            'name': 'Cliente Test',
            'is_company': True,
        })
        
        # Crear orden de venta
        self.sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product1.id,
                    'product_uom_qty': 10,
                    'product_uom': self.env.ref('uom.product_uom_unit').id,
                    'price_unit': 100,
                }),
                (0, 0, {
                    'product_id': self.product2.id,
                    'product_uom_qty': 5,
                    'product_uom': self.uom_caja.id,
                    'price_unit': 200,
                }),
            ]
        })
        
        # Confirmar la orden de venta
        self.sale_order.action_confirm()
        
        # Obtener el picking creado
        self.picking = self.sale_order.picking_ids[0]
        
        # Crear tipo de operación para pruebas
        self.picking_type_outgoing = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing')
        ], limit=1)

    def test_validate_product_in_sale_order_success(self):
        """Test: Producto válido en orden de venta"""
        # Debería pasar sin errores
        result = self.picking._validate_product_in_sale_order(
            self.product1.id, 
            self.env.ref('uom.product_uom_unit').id
        )
        self.assertTrue(result)

    def test_validate_product_not_in_sale_order(self):
        """Test: Producto no está en la orden de venta"""
        with self.assertRaises(ValidationError) as cm:
            self.picking._validate_product_in_sale_order(
                self.product3.id,
                self.env.ref('uom.product_uom_unit').id
            )
        
        self.assertIn('no está en el pedido de venta', str(cm.exception))
        self.assertIn(self.product3.display_name, str(cm.exception))
        self.assertIn(self.sale_order.name, str(cm.exception))

    def test_validate_wrong_uom(self):
        """Test: UOM incorrecta para producto en orden de venta"""
        with self.assertRaises(ValidationError) as cm:
            self.picking._validate_product_in_sale_order(
                self.product2.id,  # Este producto usa 'Caja' en la orden
                self.env.ref('uom.product_uom_unit').id  # Intentamos usar 'Unidad'
            )
        
        self.assertIn('debe usar la unidad de medida', str(cm.exception))
        self.assertIn('Caja', str(cm.exception))

    def test_validate_correct_uom(self):
        """Test: UOM correcta para producto en orden de venta"""
        result = self.picking._validate_product_in_sale_order(
            self.product2.id,
            self.uom_caja.id
        )
        self.assertTrue(result)

    def test_stock_move_create_validation(self):
        """Test: Validación en creación de stock.move"""
        # Intentar crear un move con producto que no está en la orden
        with self.assertRaises(ValidationError):
            self.env['stock.move'].create({
                'name': 'Test Move',
                'product_id': self.product3.id,
                'product_uom_qty': 1,
                'product_uom': self.env.ref('uom.product_uom_unit').id,
                'picking_id': self.picking.id,
                'location_id': self.picking.location_id.id,
                'location_dest_id': self.picking.location_dest_id.id,
            })

    def test_stock_move_write_validation(self):
        """Test: Validación en modificación de stock.move"""
        # Crear un move válido primero
        move = self.env['stock.move'].create({
            'name': 'Test Move',
            'product_id': self.product1.id,
            'product_uom_qty': 1,
            'product_uom': self.env.ref('uom.product_uom_unit').id,
            'picking_id': self.picking.id,
            'location_id': self.picking.location_id.id,
            'location_dest_id': self.picking.location_dest_id.id,
        })
        
        # Intentar cambiar a un producto no válido
        with self.assertRaises(ValidationError):
            move.write({'product_id': self.product3.id})

    def test_stock_move_line_validation(self):
        """Test: Validación en stock.move.line"""
        # Intentar crear una línea con producto no válido
        with self.assertRaises(ValidationError):
            self.env['stock.move.line'].create({
                'product_id': self.product3.id,
                'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                'qty_done': 1,
                'picking_id': self.picking.id,
                'location_id': self.picking.location_id.id,
                'location_dest_id': self.picking.location_dest_id.id,
            })

    def test_no_validation_for_non_outgoing(self):
        """Test: No validar para pickings que no son de entrega"""
        # Crear picking de recepción
        picking_incoming = self.env['stock.picking'].create({
            'picking_type_id': self.env['stock.picking.type'].search([
                ('code', '=', 'incoming')
            ], limit=1).id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            'origin': self.sale_order.name,
        })
        
        # Debería permitir cualquier producto
        result = picking_incoming._validate_product_in_sale_order(self.product3.id)
        self.assertTrue(result)

    def test_no_validation_without_origin(self):
        """Test: No validar si no hay origen (orden de venta)"""
        # Crear picking sin origen
        picking_no_origin = self.env['stock.picking'].create({
            'picking_type_id': self.picking_type_outgoing.id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        
        # Debería permitir cualquier producto
        result = picking_no_origin._validate_product_in_sale_order(self.product3.id)
        self.assertTrue(result)

    def test_barcode_validation_rpc(self):
        """Test: Validación de códigos de barras via RPC"""
        # Test producto válido
        result = self.picking.scan_product_barcode(
            self.picking.id, 
            self.product1.barcode
        )
        self.assertTrue(result['success'])
        
        # Test producto no válido
        result = self.picking.scan_product_barcode(
            self.picking.id,
            self.product3.barcode
        )
        self.assertFalse(result['success'])
        self.assertIn('no está en el pedido de venta', result['message'])

    def test_get_allowed_products(self):
        """Test: Obtener productos permitidos para picking"""
        result = self.picking.get_allowed_products_for_picking(self.picking.id)
        
        self.assertTrue(result['success'])
        self.assertFalse(result['all_products_allowed'])
        self.assertEqual(len(result['allowed_products']), 2)
        
        # Verificar que los productos correctos están en la lista
        product_ids = [p['product_id'] for p in result['allowed_products']]
        self.assertIn(self.product1.id, product_ids)
        self.assertIn(self.product2.id, product_ids)
        self.assertNotIn(self.product3.id, product_ids)

    def test_validate_product_for_picking_rpc(self):
        """Test: Validación RPC de producto específico"""
        # Producto válido
        result = self.picking.validate_product_for_picking(
            self.picking.id,
            self.product1.id,
            self.env.ref('uom.product_uom_unit').id
        )
        self.assertTrue(result['success'])
        
        # Producto no válido
        result = self.picking.validate_product_for_picking(
            self.picking.id,
            self.product3.id
        )
        self.assertFalse(result['success'])

    def test_check_picking_type_and_origin(self):
        """Test: Verificación de tipo de picking y origen"""
        # Picking con orden de venta debería requerir validación
        self.assertTrue(self.picking._check_picking_type_and_origin())
        
        # Crear picking sin origen
        picking_no_origin = self.env['stock.picking'].create({
            'picking_type_id': self.picking_type_outgoing.id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        self.assertFalse(picking_no_origin._check_picking_type_and_origin())

    def tearDown(self):
        """Limpiar después de las pruebas"""
        super().tearDown()