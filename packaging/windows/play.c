/* Play Sumeragi Native+.exe: starts the game with the settings saved by the launcher, without opening
 * the launcher (it runs the launcher executable with --play from its own folder and waits for it, so Steam
 * and other front ends see the game running). Extra arguments are passed on. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR arguments, int show)
{
    (void)instance, (void)previous, (void)show;
    static wchar_t dir[32768], exe[32768], line[32768];
    DWORD length = GetModuleFileNameW(NULL, dir, 32768);
    if (length == 0 || length >= 32768)
        return 1;
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash)
        *slash = 0;

    static const wchar_t *const candidates[] = {
        L"Sumeragi Native+.exe",
        L"Sengoku Basara 4.exe",
        L"SpartanPort.exe"
    };

    int found = 0;
    for (size_t i = 0; i < sizeof(candidates) / sizeof(candidates[0]); ++i) {
        swprintf(exe, 32768, L"%ls\\%ls", dir, candidates[i]);
        if (GetFileAttributesW(exe) != INVALID_FILE_ATTRIBUTES) {
            found = 1;
            break;
        }
    }
    if (!found) {
        swprintf(exe, 32768, L"%ls\\Sumeragi Native+.exe", dir);
    }

    swprintf(line, 32768, L"\"%ls\" --play%ls%ls", exe, arguments && *arguments ? L" " : L"",
             arguments ? arguments : L"");

    STARTUPINFOW startup = {.cb = sizeof(startup)};
    PROCESS_INFORMATION process;
    if (!CreateProcessW(exe, line, NULL, NULL, FALSE, 0, NULL, dir, &startup, &process)) {
        MessageBoxW(NULL, L"Sumeragi Native+.exe was not found next to this file.", L"Sumeragi Native+",
                    MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hProcess);
    return (int)code;
}
