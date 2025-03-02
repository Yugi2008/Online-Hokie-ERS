var socket = io()

socket.on("pong", function (data)
{
    console.log("Pong! ...with a side of: " + data)
})

socket.on("denied_entry", function (reason)
{
    gameArea.components["statusText"].text = "Denied Entry: " + reason
    gameArea.components["statusText"].fontSize = "25px"
})

socket.on("admit_players", function (playerNames)
{
    if (gameArea.numPlayers == 0)
    {
        gameArea.components["statusText"].hide()
        document.getElementById("lobbyText").innerHTML = "Lobby: " + window.location.href.split("/")[window.location.href.split("/").length - 1].split("+")[0]
    }
    else
    {
        document.getElementById("startGameButton").disabled = ""
    }
    for (let playerName of playerNames.split(","))
    {
        console.log("admit player: " + playerName)
        gameArea.drawList.push((new Player(playerName, gameArea.numPlayers)).component)

        for (let i = 0; i < gameArea.numPlayers; i++)
        {
            let theta = (i * 2 * Math.PI / gameArea.numPlayers) + (Math.PI / 2)
            gameArea.playerOrder[i].component.x = (.4 * gameArea.canvas.width) * Math.cos(theta) + gameArea.canvas.width / 2
            gameArea.playerOrder[i].component.y = (.4 * gameArea.canvas.height) * Math.sin(theta) + gameArea.canvas.height / 2
        }
    }
})

socket.on("become_host", function (isHost)
{
    becomeHost(isHost)
})

function becomeHost(isHost)
{
    for (let setting of document.getElementsByClassName("hostSetting"))
    {
        setting.disabled = isHost
    }
    if (isHost === "")
    {
        document.getElementById("youAreTheHost").style.display = ""
    }
    else
    {
        document.getElementById("youAreTheHost").style.display = "none"
    }
}

function declareSettings()
{
    socket.emit("declare_settings", getSettings())
}

socket.on("update_settings", function (settings)
{
    for (let setting in settings)
    {
        document.getElementById(setting).checked = settings[setting]
    }
})

function startGame()
{
    becomeHost("n")
    socket.emit("start_game", getSettings())
}

socket.on("players_turn", function (playerName)
{
    console.log("player's turn")
    makeTurn(playerName)
})

function makeTurn(playerName)
{
    for (let player in gameArea.players)
    {
        gameArea.players[player].isTurn = false
    }
    gameArea.players[playerName].isTurn = true
}

socket.on("prompt_deal", function ()
{
    console.log("prompt deal")
    makeTurn(gameArea.user.name)
    if (gameArea.centerStack.length > 0)
    {
        gameArea.userCanSlap = true
    }
    gameArea.userIsDealing = true
    gameArea.temp.userIsDealing = true
})

socket.on("witness_deal", function (info)
{
    console.log("witness deal")
    gameArea.components["statusText"].hide()
    gameArea.components[info.cardID].deal(gameArea.players[info.dealerName].index)
    gameArea.userCanSlap = true
})

socket.on("game_over", function (reason)
{
    console.log("Game Over! - " + reason)
    gameArea.components["statusText"].text = reason
    gameArea.components["statusText"].fontSize = "50px"
    gameArea.components["statusText"].fillStyle = "#EE4B2B"
    gameArea.drawList.push(gameArea.components["statusText"])
    gameArea.userIsDealing = false
    gameArea.userIsReceiving = false
    gameArea.userCanSlap = false
})

socket.on("prompt_receive", function ()
{
    console.log("prompt receive")
    makeTurn(gameArea.user.name)
    gameArea.userIsReceiving = true
    gameArea.temp.userIsReceiving = true
    gameArea.userCanSlap = false
})

socket.on("witness_receive", function (recipientName)
{
    console.log("witness receive")
    gameArea.userCanSlap = false
    gameArea.recipientIndex = gameArea.players[recipientName].index
    gameArea.receiveAnimationStart = gameArea.timestamp
    gameArea.audio.dealMany.play()
})

socket.on("witness_futile_slap", function (slapperName)
{
    console.log("witness futile slap")
    gameArea.players[slapperName].slapper.slap()
})

socket.on("witness_burn_slap", function (info)
{
    console.log("witness burn slap")
    gameArea.components[info.cardID].setBurn(gameArea.players[info.burnerName].index, gameArea.userIsDealing, gameArea.userIsReceiving)
    gameArea.players[info.burnerName].slapper.burnSlap(gameArea.components[info.cardID])
})

socket.on("witness_slap", function (slapperName)
{
    console.log("witness slap")
    gameArea.players[slapperName].slapper.slap()

    gameArea.userIsDealing = false
    gameArea.userIsReceiving = false
})

socket.on("explain_slap", function (explanation)
{
    console.log("explain slap")
    gameArea.components["statusText"].text = explanation
    gameArea.components["statusText"].fontSize = "70px"
    gameArea.components["statusText"].fillStyle = "#EE4B2B"
    gameArea.drawList.push(gameArea.components["statusText"])
})

socket.on("reveal_hands", function (hands)
{
    for (let playerName in hands)
    {
        gameArea.players[playerName].revealHand(hands[playerName])
    }
})
