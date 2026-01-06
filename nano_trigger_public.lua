-- Nano Banana Snapper (Pictures Edition)
function descriptor()
    return { title = "Nano Banana Snapper", version = "3.1", capabilities = {} }
end

function activate()
    -- 1. HARDCODED TARGET FOLDER
    -- We explicitly tell Python to look here.
    local target_dir = "C:\\Users\\YOUR_USER\\Pictures\\VLC Snapshots"

    local vout = vlc.object.vout()
    if vout then
        -- 2. GET MEDIA ORIENTATION (For Sideways Videos)
        local orientation = "Normal"
        local item = vlc.input.item()
        if item then
            local info = item:info()
            for cat, content in pairs(info) do
                for name, value in pairs(content) do
                    if name == "Orientation" then
                        orientation = value
                        break
                    end
                end
            end
        end

        -- 3. TRIGGER SNAPSHOT
        -- Only pause if we are currently playing.
        -- This prevents the "toggle" behavior when users manually pause first.
        if vlc.playlist.status() == "playing" then
            vlc.playlist.pause()
        end
        -- This triggers the standard VLC snapshot (which you set to Pictures in Step 1)
        vlc.var.set(vout, "video-snapshot", nil)
        
        vlc.msg.info("Nano Banana: Snapshot triggered. Orientation: " .. orientation)
        
        -- 4. LAUNCH PYTHON
        local python_exe = "python"
        local script_path = "C:\\Path\\To\\banana_snipper.py"
        
        -- Pass FOLDER and ORIENTATION
        local cmd = 'start "" "' .. python_exe .. '" "' .. script_path .. '" "' .. target_dir .. '" "' .. orientation .. '"'
        
        os.execute(cmd)
        
        -- 5. SELF-DEACTIVATE
        vlc.deactivate()
    else
        vlc.msg.err("No video found!")
    end
end

function deactivate() end
function close() vlc.deactivate() end
