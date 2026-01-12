"""
/status Command
===============

Slash command to get a formatted status embed of the player's empire.
This is a quick reference that doesn't require an LLM call.
"""

import logging
import discord
from discord import app_commands

logger = logging.getLogger(__name__)


def format_number(n: float | int | None) -> str:
    """Format a number for display.

    Args:
        n: The number to format

    Returns:
        Formatted string with thousands separators
    """
    if n is None:
        return "N/A"
    if isinstance(n, float):
        if n == int(n):
            return f"{int(n):,}"
        return f"{n:,.1f}"
    return f"{n:,}"


def format_net(n: float | int | None) -> str:
    """Format a net resource value with +/- sign.

    Args:
        n: The net value

    Returns:
        Formatted string with sign
    """
    if n is None:
        return "N/A"
    sign = "+" if n >= 0 else ""
    if isinstance(n, float):
        return f"{sign}{n:.1f}"
    return f"{sign}{n}"


def setup(bot) -> None:
    """Register the /status command with the bot.

    Args:
        bot: The StellarisBot instance
    """

    @bot.tree.command(
        name="status",
        description="Get a quick status overview of your empire (no AI call)"
    )
    async def status_command(interaction: discord.Interaction) -> None:
        """Handle the /status command.

        Args:
            interaction: The Discord interaction
        """
        # Check if save is loaded
        if not bot.companion.is_loaded:
            await interaction.response.send_message(
                "No save file is currently loaded. Please wait for a save to be detected "
                "or restart the bot with a valid save file.",
                ephemeral=True
            )
            return

        try:
            # Get raw status data (no LLM call)
            data = bot.companion.get_status_data()

            # Create embed
            embed = discord.Embed(
                title=f"{data['empire_name']} | {data['date']}",
                color=0x5865F2,  # Discord blurple
                description=bot.companion.personality_summary
            )

            # Military section
            military_text = (
                f"Power: {format_number(data.get('military_power'))}\n"
                f"Fleets: {format_number(data.get('fleet_count'))}\n"
                f"Fleet Size: {format_number(data.get('fleet_size'))}"
            )
            embed.add_field(name="Military", value=military_text, inline=True)

            # Economy section
            net = data.get('net_resources', {})
            economy_text = (
                f"Energy: {format_net(net.get('energy'))}/mo\n"
                f"Minerals: {format_net(net.get('minerals'))}/mo\n"
                f"Alloys: {format_net(net.get('alloys'))}/mo"
            )
            embed.add_field(name="Economy", value=economy_text, inline=True)

            # Research section
            research_text = (
                f"Tech Power: {format_number(data.get('tech_power'))}\n"
                f"Research: {format_net(data.get('research_summary'))}/mo"
            )
            embed.add_field(name="Research", value=research_text, inline=True)

            # Territory section
            colonies = data.get('colonies', {})
            if isinstance(colonies, dict):
                colony_count = colonies.get('total_count', 'N/A')
                total_pops = colonies.get('total_population', 'N/A')
                habitats = colonies.get('habitats', {}).get('count', 0)
                planets = colonies.get('planets', {}).get('count', 0)

                territory_text = (
                    f"Colonies: {format_number(colony_count)}\n"
                    f"Planets: {format_number(planets)}, Habitats: {format_number(habitats)}\n"
                    f"Population: {format_number(total_pops)}"
                )
            else:
                territory_text = "Data unavailable"

            embed.add_field(name="Territory", value=territory_text, inline=True)

            # Diplomacy section
            diplo = data.get('diplomacy_summary', {})
            allies = data.get('allies', [])
            federation = data.get('federation')

            diplo_text = (
                f"Contacts: {format_number(diplo.get('total_contacts', 0))}\n"
                f"Positive: {diplo.get('positive', 0)} | Negative: {diplo.get('negative', 0)}\n"
            )
            if allies:
                diplo_text += f"Allies: {len(allies)}\n"
            if federation:
                diplo_text += f"Federation: Yes"

            embed.add_field(name="Diplomacy", value=diplo_text, inline=True)

            # Add footer with companion info
            embed.set_footer(text="Use /ask for detailed analysis or /briefing for full strategic report")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in /status command: {e}")
            await interaction.response.send_message(
                f"An error occurred while getting status: {str(e)}",
                ephemeral=True
            )

    logger.info("/status command registered")
