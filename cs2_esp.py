"""
Requisitos: pip install pymem pyMeow requests
IMPORTANTE: o CS2 precisa estar em "Janela" ou "Tela cheia em janela" (borderless),
          overlay NAO aparece em tela cheia exclusiva.
"""
import struct
import time
import sys

import requests
import pymem
import pymem.process
import pyMeow as pme


# ======================= CONFIG =======================
FPS = 144
ENTITY_STRIDE = 112          # mesmo valor usado no versaofinal.py (funcionando)

ESP_BOX = True
ESP_BOX_FILL = True
ESP_HEALTHBAR = True
ESP_NAME = True
SHOW_TEAM = True            # False = desenha so inimigos

COR_INIMIGO = "red"
COR_TIME = "blue"
COR_TEXTO = "white"
COR_FUNDO_BOX = "black"
FONTE = 12

HEAD_BONE = 6                # usado so para calcular o topo do quadrado (nao desenha)
# ======================================================





class Offsets:
    pass


def carregar_offsets():
    ultimo_erro = None
    
    try:
        o = Offsets()
        o.dwEntityList = 0x0
        o.dwViewMatrix = 0x0
        o.dwLocalPlayerPawn = 0x0
        o.dwLocalPlayerController = 0x0

        o.m_iszPlayerName = 0x0
        o.m_hPlayerPawn = 0x0
        o.m_iHealth = 0x0
        o.m_iTeamNum = 0x0
        o.m_pGameSceneNode = 0x0
        o.m_vOldOrigin = 0x0
        o.m_bDormant = 0x0
        o.m_pBoneArray = 0x0 + 128

        print(f"[OK] Offsets carregadas")
        return o
    except Exception as e:
        ultimo_erro = e

    sys.exit(f"[ERRO] Nao foi possivel carregar offsets: {ultimo_erro!r}")


# ---------------------- MEMORIA -----------------------
def abrir_cs2():
    while True:
        try:
            pm = pymem.Pymem("cs2.exe")
            client = pymem.process.module_from_name(pm.process_handle, "client.dll").lpBaseOfDll
            print(f"[OK] cs2.exe encontrado | client.dll = {hex(client)}")
            return pm, client
        except Exception:
            print("[...] Aguardando cs2.exe / client.dll ...")
            time.sleep(2)


def ler_vec3(pm, addr):
    x, y, z = struct.unpack("3f", pm.read_bytes(addr, 12))
    return {"x": x, "y": y, "z": z}


def ler_matrix(pm, client, off):
    return list(struct.unpack("16f", pm.read_bytes(client + off.dwViewMatrix, 64)))


def w2s(matrix, pos):
    """Retorna {'x','y'} ou None se estiver fora da tela / atras da camera."""
    try:
        return pme.world_to_screen(matrix, pos, 1)
    except Exception:
        return None


def resolver_handle(pm, ent_list, handle):
    entry = pm.read_longlong(ent_list + 8 * ((handle & 0x7FFF) >> 9) + 16)
    if not entry:
        return 0
    return pm.read_longlong(entry + ENTITY_STRIDE * (handle & 0x1FF))


class Jogador:
    __slots__ = ("controller", "pawn", "scene", "bones", "health", "team", "name", "origin")


def ler_jogadores(pm, client, off):
    ent_list = pm.read_longlong(client + off.dwEntityList)
    if not ent_list:
        return [], 0

    local_pawn = pm.read_longlong(client + off.dwLocalPlayerPawn)
    local_team = pm.read_int(local_pawn + off.m_iTeamNum) if local_pawn else 0

    jogadores = []
    for i in range(1, 65):
        try:
            controller = resolver_handle(pm, ent_list, i)
            if not controller:
                continue

            handle = pm.read_uint(controller + off.m_hPlayerPawn)
            if not handle or handle == 0xFFFFFFFF:
                continue

            pawn = resolver_handle(pm, ent_list, handle)
            if not pawn or pawn == local_pawn:
                continue

            health = pm.read_int(pawn + off.m_iHealth)
            if health <= 0 or health > 100:
                continue

            team = pm.read_int(pawn + off.m_iTeamNum)
            if not SHOW_TEAM and team == local_team:
                continue

            scene = pm.read_longlong(pawn + off.m_pGameSceneNode)
            if not scene or pm.read_bool(scene + off.m_bDormant):
                continue

            j = Jogador()
            j.controller = controller
            j.pawn = pawn
            j.scene = scene
            j.bones = pm.read_longlong(scene + off.m_pBoneArray)
            j.health = health
            j.team = team
            j.origin = ler_vec3(pm, pawn + off.m_vOldOrigin)
            try:
                j.name = pm.read_string(controller + off.m_iszPlayerName, 32)
            except Exception:
                j.name = "?"
            jogadores.append(j)
        except Exception:
            continue

    return jogadores, local_team


def bone_pos(pm, bones, idx):
    return ler_vec3(pm, bones + idx * 32)


# ----------------------- DESENHO ----------------------
def desenhar_jogador(pm, j, matrix, local_team):
    feet = w2s(matrix, j.origin)
    if not feet:
        return

    head_world = bone_pos(pm, j.bones, HEAD_BONE) if j.bones else None
    if head_world:
        head_top = dict(head_world)
        head_top["z"] += 8.0
    else:
        head_top = {"x": j.origin["x"], "y": j.origin["y"], "z": j.origin["z"] + 72.0}

    head = w2s(matrix, head_top)
    if not head:
        return

    altura = feet["y"] - head["y"]
    if altura < 4:
        return
    largura = altura / 2
    x = head["x"] - largura / 2
    y = head["y"]

    cor = pme.get_color(COR_TIME if j.team == local_team else COR_INIMIGO)
    cor_texto = pme.get_color(COR_TEXTO)

    if ESP_BOX:
        if ESP_BOX_FILL:
            pme.draw_rectangle(x, y, largura, altura, pme.fade_color(pme.get_color(COR_FUNDO_BOX), 0.35))
        pme.draw_rectangle_lines(x, y, largura, altura, cor, 1.2)

    if ESP_HEALTHBAR:
        bar_w = 3
        bar_x = x - bar_w - 3
        hp_h = altura * (j.health / 100)
        pme.draw_rectangle(bar_x - 1, y - 1, bar_w + 2, altura + 2, pme.get_color("black"))
        r = int(255 * (1 - j.health / 100))
        g = int(255 * (j.health / 100))
        pme.draw_rectangle(bar_x, y + (altura - hp_h), bar_w, hp_h, pme.new_color(r, g, 0, 255))

    if ESP_NAME and j.name:
        tw = pme.measure_text(j.name, FONTE)
        pme.draw_text(j.name, head["x"] - tw / 2, y - FONTE - 2, FONTE, cor_texto)


def main():
    off = carregar_offsets()
    pm, client = abrir_cs2()

    # target = titulo da janela do jogo -> overlay fica em cima do CS2
    pme.overlay_init(target="Counter-Strike 2", title="base_overlay", fps=FPS)
    print("[OK] Overlay iniciado. Feche esta janela/console para sair.")

    while pme.overlay_loop():
        pme.begin_drawing()          # cs22.py esquecia o begin_drawing
        try:
            matrix = ler_matrix(pm, client, off)
            jogadores, local_team = ler_jogadores(pm, client, off)
            for j in jogadores:
                try:
                    desenhar_jogador(pm, j, matrix, local_team)
                except Exception:
                    continue
        except Exception:
            pass
        pme.end_drawing()


if __name__ == "__main__":
    main()
