from odoo import models, fields, api
from odoo.exceptions import UserError
import base64
import io
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None
    _logger.warning("La librería xlsxwriter no está instalada. Instálela con: pip install xlsxwriter")

class TradeImportation(models.Model):
    _inherit = 'trade.importation'

    def action_generate_excel_report(self):
        """Acción para generar el reporte Excel"""
        _logger.info(f"Generando reporte Excel para importación {self.id}")
        
        if self.state != 'done':
            raise UserError(f"Solo se puede generar el reporte cuando la importación está completada. Estado actual: {self.state}")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generar Reporte de Importación',
            'res_model': 'importation.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_importation_id': self.id}
        }

    def generate_importation_excel_report(self):
        """Genera el reporte Excel de la importación"""
        if not xlsxwriter:
            raise UserError("La librería xlsxwriter no está instalada. Instálela con: pip install xlsxwriter")
        
        # Verificar estado antes de generar
        if self.state != 'done':
            raise UserError(f"Solo se puede generar el reporte cuando la importación está completada. Estado actual: {self.state}")
        
        try:
            # Crear archivo Excel en memoria
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            worksheet = workbook.add_worksheet('Informe de Importación')
            
            # Configurar estilos y pasarlos a los métodos
            formats = self._setup_excel_styles(workbook)
            
            # Generar contenido del reporte
            row = 0
            row = self._write_header(worksheet, workbook, row, formats)
            row = self._write_liquidation_items_table(worksheet, workbook, row, formats)
            row = self._write_suppliers_table(worksheet, workbook, row, formats)
            row = self._write_products_table(worksheet, workbook, row, formats)
            
            workbook.close()
            output.seek(0)
            
            # Crear archivo adjunto
            filename = f"Informe_Importacion_{self.code or 'SIN_CODIGO'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(output.read()),
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            })
            
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'new',
            }
        except Exception as e:
            _logger.error(f"Error generando reporte Excel: {str(e)}")
            raise UserError(f"Error generando el reporte Excel: {str(e)}")

    def _setup_excel_styles(self, workbook):
        """Configura los estilos para el Excel y retorna un diccionario con los formatos"""
        return {
            'header_company_format': workbook.add_format({
                'bold': True,
                'font_size': 14,
                'align': 'left',
                'valign': 'vcenter',
                'bg_color': '#D9E1F2',
                'border': 1
            }),
            'header_format': workbook.add_format({
                'bold': True,
                'font_size': 14,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#D9E1F2',
                'border': 1
            }),
            'table_header_format': workbook.add_format({
                'bold': True,
                'font_size': 11,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#B4C7E7',
                'border': 1,
                'text_wrap': True
            }),
            'cell_format': workbook.add_format({
                'font_size': 10,
                'align': 'left',
                'valign': 'vcenter',
                'border': 1,
                'text_wrap': True
            }),
            'number_format': workbook.add_format({
                'font_size': 10,
                'align': 'right',
                'valign': 'vcenter',
                'border': 1,
                'num_format': '#,##0.00'
            })
        }

    def _write_header(self, worksheet, workbook, start_row, formats):
        """Escribe el encabezado del reporte"""
        current_row = start_row
        
        # 1. Logo de la compañía (si existe)
        company = self.env.company
        if company.logo:
            try:
                image_data = io.BytesIO(base64.b64decode(company.logo))
                worksheet.set_row(current_row, 60)
                worksheet.insert_image(
                    current_row, 0, "logo.png", {
                        "image_data": image_data,
                        "x_scale": 0.078,
                        "y_scale": 0.078,
                        "x_offset": 10,
                        "y_offset": 5
                    }
                )
                current_row += 1
            except Exception as e:
                _logger.warning(f"Error insertando logo: {str(e)}")
        
        # 2. Nombre de la compañía
        worksheet.merge_range(
            current_row, 0, current_row, 6, 
            company.name or 'Nombre de la Compañía', 
            formats['header_company_format']
        )
        current_row += 2
        
        # 3. Identificador de la importación
        worksheet.merge_range(
            current_row, 0, current_row, 6, 
            f"IMPORTACIÓN: {self.code or 'SIN CÓDIGO'}", 
            formats['header_company_format']
        )
        current_row += 1
        
        # 4. Valores en moneda
        currency_text = ""
        if self.currency_id:
            currency_text = f"VALORES EN {self.currency_id.name} {getattr(self.currency_id, 'symbol', '')} {getattr(self.currency_id, 'full_name', '') or ''}"
        else:
            currency_text = "VALORES EN MONEDA NO DEFINIDA"
        worksheet.merge_range(
            current_row, 0, current_row, 6, 
            currency_text, 
            formats['header_company_format']
        )
        current_row += 1
        
        # 5. Fecha de liquidación
        liq_date_text = ""
        if hasattr(self, 'liq_date') and self.liq_date:
            liq_date_text = f"FECHA DE LIQUIDACIÓN: {self.liq_date.strftime('%d/%m/%Y')}"
        elif hasattr(self, 'liquidation_date') and self.liquidation_date:
            liq_date_text = f"FECHA DE LIQUIDACIÓN: {self.liquidation_date.strftime('%d/%m/%Y')}"
        else:
            liq_date_text = "FECHA DE LIQUIDACIÓN: NO DEFINIDA"
        worksheet.merge_range(
            current_row, 0, current_row, 6, 
            liq_date_text, 
            formats['header_company_format']
        )
        current_row += 3
        
        return current_row

    def _get_liquidation_items(self):
        """
        Devuelve las líneas de liquidación cuyo concepto tiene is_landed_cost = True,
        independientemente del nombre del campo Many2one o de si existe un one2many
        en la importación.
        """
        for field_name in ['liquidation_ids', 'liquidations_ids']:
            if hasattr(self, field_name):
                records = getattr(self, field_name).filtered(
                    lambda r: getattr(r.concept_id, 'is_landed_cost', False)
                )
                if records:
                    return records

        fk_names = ['importation_liq_id', 'importation_id', 'imp_id']
        for fk in fk_names:
            if fk in self.env['trade.importation.liquidation']._fields:
                return self.env['trade.importation.liquidation'].search([
                    (fk, '=', self.id),
                    ('concept_id.is_landed_cost', '=', True),
                ])

        return self.env['trade.importation.liquidation']  # colección vacía

    def _get_product_price_from_cost_details(self, product_id):
        """Obtiene el precio de un producto desde la tabla cost_details - específicamente el subtotal"""
        try:
            # Buscar en cost_details el producto específico
            cost_details = []
            # Priorizar el modelo correcto trade.cost.details
            model_names = ['trade.cost.details', 'trade.costo_details', 'importation.cost.details', 'cost.details']
            
            for model_name in model_names:
                try:
                    if model_name in self.env:
                        cost_details = self.env[model_name].search([
                            ('importation_id', '=', self.id),
                            ('product_id', '=', product_id)
                        ])
                        if cost_details:
                            break
                except Exception as e:
                    continue
            
            if not cost_details:
                # Buscar por relaciones directas
                for field_name in ['cost_details_ids', 'cost_detail_ids', 'costo_details_ids']:
                    if hasattr(self, field_name):
                        try:
                            all_details = getattr(self, field_name)
                            cost_details = all_details.filtered(lambda d: d.product_id.id == product_id)
                            if cost_details:
                                break
                        except Exception as e:
                            continue
            
            if cost_details:
                detail = cost_details[0]  # Tomar el primer registro
                
                # PRIORIZAR EL SUBTOTAL - campo foreign_former_company_currency_cost del modelo trade.cost.details
                subtotal_fields = [
                    'foreign_unit_company_currency_cost',  # Campo CONFIRMADO del subtotal en trade.cost.details

                ]
                
                for field in subtotal_fields:
                    if hasattr(detail, 'product_qty') and hasattr(detail, 'foreign_unit_company_currency_cost'):
                        qty = getattr(detail, 'product_qty', 0.0) or 0.0
                        unit_cost = getattr(detail, 'foreign_unit_company_currency_cost', 0.0) or 0.0
                        subtotal_value = qty * unit_cost
                        if subtotal_value > 0:
                            _logger.info(f"Subtotal obtenido para producto {product_id} desde campo {field}: {subtotal_value}")
                            return subtotal_value
                
                # Si no encuentra subtotal directo, intentar campos alternativos
                alternative_fields = [
                    'foreign_final_currency_cost',           # Total liquidado
                    'foreign_unit_company_currency_cost',    # Precio unitario
                ]
                
                for field in alternative_fields:
                    if hasattr(detail, field):
                        price_value = getattr(detail, field, 0.0) or 0.0
                        if price_value > 0:
                            _logger.warning(f"Usando campo alternativo {field} para producto {product_id}: {price_value}")
                            return price_value
                
                # Como último recurso, calcular qty * precio unitario
                if hasattr(detail, 'product_qty') and hasattr(detail, 'foreign_unit_company_currency_cost'):
                    qty = getattr(detail, 'product_qty', 0.0) or 0.0
                    unit_cost = getattr(detail, 'foreign_unit_company_currency_cost', 0.0) or 0.0
                    if qty > 0 and unit_cost > 0:
                        calculated_subtotal = qty * unit_cost
                        _logger.info(f"Subtotal calculado para producto {product_id}: {qty} * {unit_cost} = {calculated_subtotal}")
                        return calculated_subtotal
            
            _logger.warning(f"No se encontró subtotal para producto {product_id}")
            return 0.0
            
        except Exception as e:
            _logger.error(f"Error obteniendo subtotal para producto {product_id}: {str(e)}")
            return 0.0

    def _write_liquidation_items_table(self, worksheet, workbook, start_row, formats):
        """Escribe la tabla de ítems de liquidación"""
        current_row = start_row
        
        # Título de la tabla
        worksheet.merge_range(
            current_row, 0, current_row, 2, 
            "ÍTEMS DE LIQUIDACIÓN", 
            formats['header_format']
        )
        current_row += 1
        
        # Encabezados de la tabla
        worksheet.write(current_row, 0, "IdGasto", formats['table_header_format'])
        worksheet.write(current_row, 1, "Importe", formats['table_header_format'])
        worksheet.write(current_row, 2, "Total Distr.", formats['table_header_format'])
        current_row += 1
        
        # Obtener ítems de liquidación con is_landed_cost=True
        liquidation_items = self._get_liquidation_items()
        
        # Escribir los ítems encontrados
        for item in liquidation_items:
            try:
                # IdGasto - código del producto del concepto
                id_gasto = ""
                if item.concept_id:
                    if hasattr(item.concept_id, 'product_id') and item.concept_id.product_id:
                        id_gasto = item.concept_id.product_id.default_code or item.concept_id.product_id.name or ""
                    elif hasattr(item.concept_id, 'code'):
                        id_gasto = item.concept_id.code or ""
                    elif hasattr(item.concept_id, 'name'):
                        id_gasto = item.concept_id.name or ""
                
                # CORREGIDO: Obtener importe del ítem de liquidación
                importe = self._get_liquidation_item_amount(item)
                
                # CORREGIDO: Calcular Total Distr. para distribución manual
                total_distr = 0.0
                is_manual_distribution = (hasattr(item, 'split_method') and item.split_method == 'manual')
                
                if is_manual_distribution:
                    # Para distribución manual: sumar costos de productos distribuidos
                    total_distr = self._calculate_manual_distribution_total_fixed(item)
                    _logger.info(f"Total distribución manual calculado para ítem {item.id}: {total_distr}")
                else:
                    # Para otros métodos usar el cálculo existente
                    total_distr = self._calculate_distribution_total(item)
                
                # Escribir la fila principal del ítem de liquidación
                worksheet.write(current_row, 0, id_gasto, formats['cell_format'])
                worksheet.write(current_row, 1, importe, formats['number_format'])
                worksheet.write(current_row, 2, total_distr, formats['number_format'])
                current_row += 1
                
                _logger.info(f"Ítem escrito: IdGasto={id_gasto}, Importe={importe}, Total Distr={total_distr}")
                
                # Mostrar productos distribuidos manualmente como sub-filas
                #if is_manual_distribution:
                #   current_row = self._write_manual_distribution_details(worksheet, workbook, current_row, formats, item)
                            
            except Exception as e:
                _logger.warning(f"Error escribiendo ítem de liquidación: {str(e)}")
                continue
        
        # Si no hay ítems, agregar una línea indicándolo
        if not liquidation_items:
            worksheet.write(current_row, 0, "No se encontraron ítems de liquidación con costo en destino", formats['cell_format'])
            worksheet.merge_range(current_row, 1, current_row, 2, "", formats['cell_format'])
            current_row += 1
        
        current_row += 2
        return current_row

    def _get_liquidation_item_amount(self, item):
        """Obtiene el importe del ítem de liquidación, incluyendo casos de distribución manual"""
        try:
            # Método 1: Campos directos del ítem
            amount_fields = ['total_amount', 'amount', 'cost', 'value', 'price', 'total']
            for field in amount_fields:
                if hasattr(item, field):
                    field_value = getattr(item, field, 0.0) or 0.0
                    if field_value != 0.0:
                        _logger.info(f"Importe obtenido del campo {field}: {field_value}")
                        return field_value
            
            # Método 2: Para distribución manual, buscar en manual.distribution.cost
            if hasattr(item, 'split_method') and item.split_method == 'manual':
                manual_distribution = self.env['manual.distribution.cost'].search([
                    ('importation_liquidation_id', '=', item.id)
                ], limit=1)
                
                if manual_distribution:
                    # Buscar campos de importe en manual.distribution.cost
                    manual_amount_fields = ['total_amount', 'amount', 'cost_amount', 'distribution_amount']
                    for field in manual_amount_fields:
                        if hasattr(manual_distribution, field):
                            field_value = getattr(manual_distribution, field, 0.0) or 0.0
                            if field_value != 0.0:
                                _logger.info(f"Importe manual obtenido del campo {field}: {field_value}")
                                return field_value
            
            # Método 3: Buscar en la relación con conceptos
            if hasattr(item, 'concept_id') and item.concept_id:
                concept_amount_fields = ['amount', 'cost', 'value', 'price']
                for field in concept_amount_fields:
                    if hasattr(item.concept_id, field):
                        field_value = getattr(item.concept_id, field, 0.0) or 0.0
                        if field_value != 0.0:
                            _logger.info(f"Importe del concepto obtenido del campo {field}: {field_value}")
                            return field_value
            
            _logger.warning(f"No se pudo obtener importe para ítem de liquidación {item.id}")
            return 0.0
            
        except Exception as e:
            _logger.error(f"Error obteniendo importe del ítem de liquidación {item.id}: {str(e)}")
            return 0.0

    def _calculate_manual_distribution_total_fixed(self, liquidation_item):
        """Versión corregida del cálculo de distribución manual"""
        try:
            total_distributed = 0.0
            
            # Buscar líneas de distribución manual
            distribution_lines = self._get_manual_distribution_lines(liquidation_item)
            
            _logger.info(f"Líneas de distribución encontradas para ítem {liquidation_item.id}: {len(distribution_lines)}")
            
            if not distribution_lines:
                _logger.warning(f"No se encontraron líneas de distribución para ítem {liquidation_item.id}")
                return 0.0
            
            # Para cada línea de distribución, obtener el costo del producto
            for line in distribution_lines:
                try:
                    # Obtener product_id de la línea
                    product_id = self._get_product_id_from_distribution_line(line)
                    
                    if product_id:
                        # CORREGIDO: Obtener el costo distribuido específico para esta línea
                        product_cost = self._get_distributed_product_cost(line, product_id)
                        total_distributed += product_cost
                        _logger.info(f"Producto {product_id}: costo distribuido {product_cost}, total acumulado: {total_distributed}")
                    else:
                        _logger.warning(f"No se pudo obtener product_id de la línea de distribución")
                        
                except Exception as e:
                    _logger.warning(f"Error procesando línea de distribución: {str(e)}")
                    continue
            
            _logger.info(f"Total distribución manual final para ítem {liquidation_item.id}: {total_distributed}")
            return total_distributed
            
        except Exception as e:
            _logger.error(f"Error calculando total de distribución manual: {str(e)}")
            return 0.0

    def _get_manual_distribution_lines(self, liquidation_item):
        """Obtiene las líneas de distribución manual para un ítem de liquidación"""
        try:
            distribution_lines = []
            
            # Método 1: Buscar por manual.distribution.cost
            manual_distribution = self.env['manual.distribution.cost'].search([
                ('importation_liquidation_id', '=', liquidation_item.id)
            ], limit=1)
            
            if manual_distribution and hasattr(manual_distribution, 'manual_distribution_cost_lines'):
                distribution_lines = manual_distribution.manual_distribution_cost_lines
                _logger.info(f"Líneas encontradas via manual.distribution.cost: {len(distribution_lines)}")
            
            # Método 2: Buscar directamente las líneas si no se encontró por el método anterior
            if not distribution_lines:
                line_models = ['manual.distribution.cost.line', 'manual.distribution.line']
                for model_name in line_models:
                    if model_name in self.env:
                        search_fields = ['liquidation_id', 'importation_liquidation_id', 'cost_id', 'manual_distribution_cost_id']
                        for field in search_fields:
                            try:
                                if field in self.env[model_name]._fields:
                                    lines = self.env[model_name].search([(field, '=', liquidation_item.id)])
                                    if lines:
                                        distribution_lines = lines
                                        _logger.info(f"Líneas encontradas via {model_name}.{field}: {len(lines)}")
                                        break
                            except Exception as e:
                                continue
                        if distribution_lines:
                            break
            
            return distribution_lines
            
        except Exception as e:
            _logger.error(f"Error obteniendo líneas de distribución manual: {str(e)}")
            return []

    def _get_product_id_from_distribution_line(self, line):
        """Obtiene el product_id de una línea de distribución"""
        try:
            product_fields = ['product_id', 'product', 'item_id']
            for p_field in product_fields:
                if hasattr(line, p_field):
                    product = getattr(line, p_field)
                    if product and hasattr(product, 'id'):
                        return product.id
            return None
        except Exception as e:
            _logger.error(f"Error obteniendo product_id de línea de distribución: {str(e)}")
            return None

    def _get_distributed_product_cost(self, distribution_line, product_id):
        """Obtiene el costo distribuido usando los MISMOS campos que la tabla de productos"""
        try:
            # CORREGIDO: Usar exactamente los mismos campos y cálculos que _write_products_table
            cost_details = self._get_cost_details_for_product(product_id)
            
            if not cost_details:
                _logger.warning(f"No se encontró cost_details para producto {product_id}")
                return 0.0
            
            # Verificar si el producto realmente tiene distribución manual
            has_distribution = self._product_has_manual_distribution(distribution_line, product_id)
            if not has_distribution:
                _logger.info(f"Producto {product_id} no tiene distribución manual válida")
                return 0.0
            
            # USAR LOS MISMOS CAMPOS QUE EN LA TABLA DE PRODUCTOS
            # Estos son los campos que usa _write_products_table:
            foreign_former_cost = getattr(cost_details, 'foreign_former_company_currency_cost', 0.0) or 0.0
            
            # Si foreign_former_cost es 0, calcular como en la tabla de productos
            if foreign_former_cost == 0.0:
                product_qty = getattr(cost_details, 'product_qty', 0.0) or 0.0
                foreign_unit_cost = getattr(cost_details, 'foreign_unit_company_currency_cost', 0.0) or 0.0
                foreign_former_cost = product_qty * foreign_unit_cost
            
            _logger.info(f"Costo obtenido para producto {product_id} (igual que tabla productos): {foreign_former_cost}")
            return foreign_former_cost
            
        except Exception as e:
            _logger.error(f"Error obteniendo costo distribuido para producto {product_id}: {str(e)}")
            return 0.0

    def _get_cost_details_for_product(self, product_id):
        """Obtiene cost_details para un producto usando la misma lógica que _write_products_table"""
        try:
            cost_details = None
            
            # Usar exactamente la misma búsqueda que en _write_products_table
            model_names = ['trade.costo_details', 'trade.cost.details', 'importation.cost.details', 'cost.details']
            for model_name in model_names:
                try:
                    if model_name in self.env:
                        cost_details = self.env[model_name].search([
                            ('importation_id', '=', self.id),
                            ('product_id', '=', product_id)
                        ], limit=1)
                        if cost_details:
                            break
                except Exception as e:
                    continue
            
            # Fallback usando campos de relación
            if not cost_details:
                for field_name in ['cost_details_ids', 'cost_detail_ids', 'costo_details_ids']:
                    if hasattr(self, field_name):
                        try:
                            all_details = getattr(self, field_name)
                            cost_details = all_details.filtered(lambda d: d.product_id.id == product_id)
                            if cost_details:
                                cost_details = cost_details[0]  # Tomar el primero
                                break
                        except Exception as e:
                            continue
            
            return cost_details
            
        except Exception as e:
            _logger.error(f"Error obteniendo cost_details para producto {product_id}: {str(e)}")
            return None

    def _product_has_manual_distribution(self, distribution_line, product_id):
        """Verifica si un producto realmente tiene distribución manual válida"""
        try:
            # Verificar que la línea de distribución tenga cantidad > 0
            qty_fields = ['qty', 'quantity', 'product_qty', 'distributed_qty']
            has_qty = False
            
            for q_field in qty_fields:
                if hasattr(distribution_line, q_field):
                    qty_value = getattr(distribution_line, q_field, 0.0) or 0.0
                    if qty_value > 0:
                        has_qty = True
                        _logger.info(f"Producto {product_id} tiene cantidad distribuida: {qty_value}")
                        break
            
            if not has_qty:
                _logger.info(f"Producto {product_id} no tiene cantidad distribuida")
                return False
            
            # Verificar que el producto tenga costo en cost_details
            cost_details = self._get_cost_details_for_product(product_id)
            if not cost_details:
                _logger.info(f"Producto {product_id} no tiene cost_details")
                return False
            
            # Verificar que tenga costo > 0
            foreign_former_cost = getattr(cost_details, 'foreign_former_company_currency_cost', 0.0) or 0.0
            if foreign_former_cost == 0.0:
                product_qty = getattr(cost_details, 'product_qty', 0.0) or 0.0
                foreign_unit_cost = getattr(cost_details, 'foreign_unit_company_currency_cost', 0.0) or 0.0
                foreign_former_cost = product_qty * foreign_unit_cost
            
            if foreign_former_cost <= 0:
                _logger.info(f"Producto {product_id} no tiene costo válido: {foreign_former_cost}")
                return False
            
            _logger.info(f"Producto {product_id} tiene distribución manual válida")
            return True
            
        except Exception as e:
            _logger.error(f"Error verificando distribución manual para producto {product_id}: {str(e)}")
            return False

    def _calculate_distribution_total(self, liquidation_item):
        """Calcula el total de distribución según el método"""
        try:
            if hasattr(liquidation_item, 'split_method') and liquidation_item.split_method == 'manual':
                total_distributed = 0.0
                
                # Buscar líneas de distribución manual
                manual_distribution = self.env['manual.distribution.cost'].search([
                    ('importation_liquidation_id', '=', liquidation_item.id)
                ], limit=1)
                
                distribution_lines = []
                if manual_distribution and hasattr(manual_distribution, 'manual_distribution_cost_lines'):
                    distribution_lines = manual_distribution.manual_distribution_cost_lines
                else:
                    # Búsqueda alternativa de líneas de distribución
                    line_models = ['manual.distribution.cost.line', 'manual.distribution.line']
                    for model_name in line_models:
                        if model_name in self.env:
                            search_fields = ['liquidation_id', 'importation_liquidation_id', 'cost_id']
                            for field in search_fields:
                                try:
                                    lines = self.env[model_name].search([(field, '=', liquidation_item.id)])
                                    if lines:
                                        distribution_lines = lines
                                        break
                                except:
                                    continue
                            if distribution_lines:
                                break
                
                _logger.info(f"Calculando distribución manual para ítem {liquidation_item.id}: {len(distribution_lines)} líneas")
                
                # Para cada línea de distribución, obtener el producto y su costo desde trade.cost.details
                for line in distribution_lines:
                    try:
                        # Obtener el product_id de la línea de distribución
                        product_id = None
                        product_fields = ['product_id', 'product', 'item_id']
                        for p_field in product_fields:
                            if hasattr(line, p_field):
                                product = getattr(line, p_field)
                                if product and hasattr(product, 'id'):
                                    product_id = product.id
                                    break
                        
                        if product_id:
                            # Buscar en trade.cost.details el foreign_former_company_currency_cost del producto
                            cost_details = self.env['trade.cost.details'].search([
                                ('importation_id', '=', self.id),
                                ('product_id', '=', product_id)
                            ], limit=1)
                            
                            if not cost_details:
                                # Búsqueda alternativa en trade.costo_details
                                cost_details = self.env['trade.costo_details'].search([
                                    ('importation_id', '=', self.id),
                                    ('product_id', '=', product_id)
                                ], limit=1)
                            
                            if cost_details:
                                # Sumar el foreign_former_company_currency_cost
                                product_cost = getattr(cost_details, 'foreign_former_company_currency_cost', 0.0) or 0.0
                                total_distributed += product_cost
                                _logger.info(f"Producto {product_id}: costo {product_cost}, total acumulado: {total_distributed}")
                            else:
                                _logger.warning(f"No se encontró cost_details para producto {product_id}")
                        else:
                            _logger.warning(f"No se pudo obtener product_id de la línea de distribución")
                            
                    except Exception as e:
                        _logger.warning(f"Error procesando línea de distribución: {str(e)}")
                        continue
                
                _logger.info(f"Total distribución manual para ítem {liquidation_item.id}: {total_distributed}")
                return total_distributed
                
            else:
                # Para métodos de distribución no manuales, usar la lógica existente
                try:
                    request_notes = self.env['trade.importation.request.note'].search([
                        ('importation_id', '=', self.id)
                    ])
                    total = sum(getattr(note, 'subtotal', 0.0) or 0.0 for note in request_notes)
                    _logger.info(f"Total distribución automática: {total}")
                    return total
                except Exception as e:
                    _logger.warning(f"Error calculando distribución automática: {str(e)}")
                    return 0.0
                    
        except Exception as e:
            _logger.warning(f"Error calculando total de distribución: {str(e)}")
            return 0.0

    def _write_suppliers_table(self, worksheet, workbook, start_row, formats):
        """Escribe la tabla de proveedores"""
        current_row = start_row
        
        worksheet.merge_range(
            current_row, 0, current_row, 2, 
            "PROVEEDORES", 
            formats['header_format']
        )
        current_row += 1
        
        suppliers = set()
        purchase_field = None
        for field_name in ['purchase_ids', 'purchase_order_ids', 'order_ids']:
            if hasattr(self, field_name):
                purchase_field = field_name
                break
        
        if purchase_field:
            try:
                purchases = getattr(self, purchase_field)
                for purchase in purchases:
                    if hasattr(purchase, 'partner_id') and purchase.partner_id:
                        vat = getattr(purchase.partner_id, 'vat', '') or 'S/VAT'
                        name = getattr(purchase.partner_id, 'complete_name', '') or getattr(purchase.partner_id, 'name', '')
                        supplier_text = f"{vat} - {name}"
                        suppliers.add(supplier_text)
            except Exception as e:
                _logger.warning(f"Error obteniendo proveedores: {str(e)}")
        
        for supplier in sorted(suppliers):
            worksheet.merge_range(
                current_row, 0, current_row, 2, 
                supplier,
                formats['cell_format']
            )
            current_row += 1
        
        if not suppliers:
            worksheet.write(current_row, 0, "No se encontraron proveedores", formats['cell_format'])
            current_row += 1
        
        current_row += 2
        return current_row

    def _write_products_table(self, worksheet, workbook, start_row, formats):
        """Escribe la tabla de productos"""
        current_row = start_row
        
        worksheet.merge_range(
            current_row, 0, current_row, 6, 
            "PRODUCTOS - COSTO EN DIVISA", 
            formats['header_format']
        )
        current_row += 1
        
        headers = ["IdOrden", "Descripción", "Recibida", "Precio", "Sub-total", "Costo unitario", "Total liquidado"]
        for col, header in enumerate(headers):
            worksheet.write(current_row, col, header, formats['table_header_format'])
        current_row += 1
        
        cost_details = []
        _logger.info(f"Buscando detalles de costo para importación {self.id}")
        
        try:
            model_names = ['trade.costo_details', 'trade.cost.details', 'importation.cost.details', 'cost.details']
            for model_name in model_names:
                try:
                    if model_name in self.env:
                        cost_details = self.env[model_name].search([
                            ('importation_id', '=', self.id)
                        ])
                        if cost_details:
                            _logger.info(f"Encontrados {len(cost_details)} detalles de costo en modelo {model_name}")
                            break
                except Exception as e:
                    continue
            if not cost_details:
                for field_name in ['cost_details_ids', 'cost_detail_ids', 'costo_details_ids']:
                    if hasattr(self, field_name):
                        try:
                            cost_details = getattr(self, field_name)
                            if cost_details:
                                _logger.info(f"Encontrados {len(cost_details)} detalles de costo en campo {field_name}")
                                break
                        except Exception as e:
                            continue
        except Exception as e:
            _logger.warning(f"Error obteniendo detalles de costo: {str(e)}")
            cost_details = []
        
        for detail in cost_details:
            try:
                id_orden = ""
                purchase_fields = ['purchase_id', 'purchase_order_id', 'order_id', 'purchase_line_id']
                for field in purchase_fields:
                    if hasattr(detail, field):
                        purchase_obj = getattr(detail, field)
                        if purchase_obj:
                            if hasattr(purchase_obj, 'order_id'):
                                purchase_obj = purchase_obj.order_id
                            if hasattr(purchase_obj, 'name'):
                                id_orden = purchase_obj.name
                                break
                            elif hasattr(purchase_obj, 'number'):
                                id_orden = purchase_obj.number
                                break
                if not id_orden and hasattr(detail, 'product_id') and detail.product_id:
                    purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', detail.product_id.id),
                        ('order_id.state', 'in', ['purchase', 'done'])
                    ])
                    for line in purchase_lines:
                        if hasattr(self, 'purchase_ids') and line.order_id in self.purchase_ids:
                            id_orden = line.order_id.name
                            break
                        elif hasattr(self, 'purchase_order_ids') and line.order_id in self.purchase_order_ids:
                            id_orden = line.order_id.name
                            break
                _logger.info(f"IdOrden para producto {detail.product_id.name if hasattr(detail, 'product_id') and detail.product_id else 'Sin producto'}: {id_orden}")
                descripcion = ""
                if hasattr(detail, 'product_id') and detail.product_id:
                    descripcion = getattr(detail.product_id, 'name', '') or ""
                product_qty = getattr(detail, 'product_qty', 0.0) or 0.0
                foreign_unit_cost = getattr(detail, 'foreign_unit_company_currency_cost', 0.0) or 0.0
                foreign_former_cost = getattr(detail, 'foreign_former_company_currency_cost', 0.0) or 0.0
                foreign_final_unit_cost = getattr(detail, 'foreign_final_product_company_cost', 0.0) or 0.0
                foreign_final_cost = getattr(detail, 'foreign_final_currency_cost', 0.0) or 0.0
                subtotal = foreign_former_cost
                if subtotal == 0.0:
                    subtotal = product_qty * foreign_unit_cost
                worksheet.write(current_row, 0, id_orden, formats['cell_format'])
                worksheet.write(current_row, 1, descripcion, formats['cell_format'])
                worksheet.write(current_row, 2, product_qty, formats['number_format'])
                worksheet.write(current_row, 3, foreign_unit_cost, formats['number_format'])
                worksheet.write(current_row, 4, subtotal, formats['number_format'])
                worksheet.write(current_row, 5, foreign_final_unit_cost, formats['number_format'])
                worksheet.write(current_row, 6, foreign_final_cost, formats['number_format'])
                current_row += 1
            except Exception as e:
                _logger.warning(f"Error procesando detalle de costo {detail.id if hasattr(detail, 'id') else 'sin ID'}: {str(e)}")
                continue
        if not cost_details:
            worksheet.write(current_row, 0, "No se encontraron productos", formats['cell_format'])
            for col in range(1, 7):
                worksheet.write(current_row, col, "", formats['cell_format'])
            current_row += 1
        worksheet.set_column('A:A', 15)
        worksheet.set_column('B:B', 30)
        worksheet.set_column('C:G', 12)
        return current_row
