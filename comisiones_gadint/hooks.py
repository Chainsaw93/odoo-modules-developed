# -*- coding: utf-8 -*-

def post_init_hook(env):
    """
    Hook ejecutado después de la instalización/actualización del módulo
    Corrige automáticamente los porcentajes mal configurados
    """
    # CORRECCIÓN DIRECTA CON SQL - MUCHO MÁS EFICIENTE
    cr = env.cr
    
    # 1. Corregir rates sobre-normalizados (500% → 5%, 1000% → 10%, etc.)
    cr.execute("""
        UPDATE sale_commission_plan_achievement 
        SET rate = rate / 100 
        WHERE type = 'amount_collected' 
        AND rate >= 100
    """)
    fixed_achievements = cr.rowcount
    print(f"Hook SQL: {fixed_achievements} achievements corregidos (rates >= 100%)")
    
    # 2. Corregir porcentajes de líderes en decimal (0.01 → 1, 0.05 → 5)
    cr.execute("""
        UPDATE gadint_external_salesperson 
        SET leader_percentage = leader_percentage * 100 
        WHERE seller_type = 'leader' 
        AND leader_percentage > 0 
        AND leader_percentage < 1
    """)
    fixed_leaders = cr.rowcount
    print(f"Hook SQL: {fixed_leaders} líderes corregidos (formato decimal)")
    
    # 3. Configurar líderes sin porcentaje a 1%
    cr.execute("""
        UPDATE gadint_external_salesperson 
        SET leader_percentage = 1.0 
        WHERE seller_type = 'leader' 
        AND (leader_percentage = 0 OR leader_percentage IS NULL)
    """)
    fixed_zero_leaders = cr.rowcount
    print(f"Hook SQL: {fixed_zero_leaders} líderes configurados a 1% (eran 0%)")
    
    # 4. Limpiar porcentajes de vendedores regulares
    cr.execute("""
        UPDATE gadint_external_salesperson 
        SET leader_percentage = 0.0 
        WHERE seller_type = 'salesperson' 
        AND leader_percentage != 0
    """)
    fixed_salespeople = cr.rowcount
    print(f"Hook SQL: {fixed_salespeople} vendedores limpiados (% a 0)")
    
    total_fixed = fixed_achievements + fixed_leaders + fixed_zero_leaders + fixed_salespeople
    print(f"Hook SQL COMPLETADO: {total_fixed} registros corregidos en total")
    
    # 5. Forzar actualización de los campos computed de display
    try:
        salespeople = env['gadint.external.salesperson'].search([])
        for salesperson in salespeople:
            salesperson._compute_commission_rate_display()
        print(f"Hook: {len(salespeople)} vendedores externos - display actualizado")
    except Exception as e:
        print(f"Hook: Error actualizando display: {e}")

def post_load_hook():
    """
    Hook ejecutado cada vez que se carga el módulo
    """
    pass